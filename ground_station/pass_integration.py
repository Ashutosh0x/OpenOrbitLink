"""
OpenOrbitLink Pass Integration -- DTN Queue Flush During Satellite Passes

Coordinates between the PassScheduler, BundleStore, and LoRa driver to
transmit queued messages during satellite overhead windows while respecting
ISM duty cycle limits.

This module is used by the GroundStationDaemon to automate the
"wait for pass -> burst transmit -> confirm" cycle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, Protocol

logger = logging.getLogger("OpenOrbitLink.PassIntegration")


class TxStatus(IntEnum):
    """Result of a single packet transmission attempt."""
    SUCCESS = 0
    DUTY_CYCLE_EXCEEDED = 1
    TX_HARDWARE_ERROR = 2
    PASS_ENDED = 3
    NO_PACKETS = 4


@dataclass
class TxResult:
    """Result of transmitting a single packet."""
    status: TxStatus
    packet_size: int = 0
    airtime_ms: float = 0.0
    rssi: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PassTxReport:
    """Summary of all transmissions during a single pass."""
    satellite_name: str
    pass_start: str
    pass_end: str
    duration_s: float
    packets_attempted: int = 0
    packets_sent: int = 0
    packets_failed: int = 0
    total_airtime_ms: float = 0.0
    duty_cycle_used_pct: float = 0.0
    stop_reason: str = ""


class TransmitDriver(Protocol):
    """Protocol for LoRa TX hardware (or simulation)."""

    async def transmit(self, data: bytes, frequency_offset_hz: float = 0) -> TxResult:
        ...

    @property
    def is_connected(self) -> bool:
        ...


class BundleSource(Protocol):
    """Protocol for bundle storage retrieval."""

    def get_pending(self, limit: int = 50) -> list:
        ...

    def mark_transmitted(self, bundle_id: str) -> None:
        ...

    def mark_failed(self, bundle_id: str) -> None:
        ...

    def increment_retry(self, bundle_id: str) -> None:
        ...


@dataclass
class DutyCycleTracker:
    """
    ISM 868 MHz duty cycle tracker.

    EU regulation: 1% duty cycle = 36 seconds per hour maximum TX time.
    Tracks cumulative airtime within a rolling 1-hour window.
    """
    budget_s: float = 36.0         # 1% of 3600s
    window_s: float = 3600.0       # 1-hour rolling window
    _tx_log: list[tuple[float, float]] = field(default_factory=list)

    def record_tx(self, airtime_s: float) -> None:
        """Record a transmission."""
        self._tx_log.append((time.time(), airtime_s))
        self._prune()

    def used_airtime_s(self) -> float:
        """Total airtime used in current window."""
        self._prune()
        return sum(airtime for _, airtime in self._tx_log)

    def remaining_s(self) -> float:
        """Remaining TX budget in seconds."""
        return max(0.0, self.budget_s - self.used_airtime_s())

    def can_transmit(self, airtime_s: float) -> bool:
        """Check if a transmission of given airtime fits the budget."""
        return self.remaining_s() >= airtime_s

    def utilization_pct(self) -> float:
        """Current duty cycle utilization as percentage."""
        return (self.used_airtime_s() / self.budget_s) * 100.0

    def _prune(self) -> None:
        """Remove entries older than the rolling window."""
        cutoff = time.time() - self.window_s
        self._tx_log = [(t, a) for t, a in self._tx_log if t > cutoff]


def estimate_packet_airtime_s(
    payload_bytes: int,
    sf: int = 12,
    bw_hz: int = 125_000,
    cr: int = 5,
    preamble_symbols: int = 8,
    explicit_header: bool = True,
    low_data_rate_opt: bool = True,
) -> float:
    """
    Estimate LoRa packet airtime using Semtech SX1276 formulas.

    Based on Semtech AN1200.13 "LoRa Modem Designer's Guide".

    Returns:
        Airtime in seconds
    """
    # Symbol duration
    t_sym = (2 ** sf) / bw_hz

    # Preamble duration
    t_preamble = (preamble_symbols + 4.25) * t_sym

    # Payload symbol count
    de = 1 if low_data_rate_opt and sf >= 11 else 0
    ih = 0 if explicit_header else 1

    numerator = 8 * payload_bytes - 4 * sf + 28 + 16 - 20 * ih
    denominator = 4 * (sf - 2 * de)

    if denominator <= 0:
        n_payload = 8
    else:
        n_payload = 8 + max(0, math.ceil(numerator / denominator)) * cr

    t_payload = n_payload * t_sym
    return t_preamble + t_payload


import math  # noqa: E402 (needed for estimate_packet_airtime_s)


class PassTransmitter:
    """
    Manages packet transmission during a satellite pass window.

    Lifecycle:
    1. Pass starts (elevation > threshold)
    2. Pull pending bundles from BundleStore, sorted by priority
    3. For each bundle:
       a. Check duty cycle budget
       b. Compute Doppler offset (if compensator available)
       c. Transmit via LoRa driver
       d. Mark bundle as TRANSMITTED or increment retry
    4. Pass ends (elevation < threshold or all bundles sent)
    5. Generate PassTxReport
    """

    def __init__(
        self,
        tx_driver: TransmitDriver,
        bundle_source: BundleSource,
        duty_cycle: Optional[DutyCycleTracker] = None,
        inter_packet_gap_ms: float = 200.0,
        max_payload_bytes: int = 80,
    ):
        self.tx_driver = tx_driver
        self.bundle_source = bundle_source
        self.duty_cycle = duty_cycle or DutyCycleTracker()
        self.inter_packet_gap_ms = inter_packet_gap_ms
        self.max_payload_bytes = max_payload_bytes

    async def transmit_during_pass(
        self,
        satellite_name: str,
        pass_duration_s: float,
        doppler_offset_fn=None,
    ) -> PassTxReport:
        """
        Burst-transmit queued bundles during a satellite pass.

        Args:
            satellite_name: Name of the overhead satellite
            pass_duration_s: Expected pass duration in seconds
            doppler_offset_fn: Optional callable(elapsed_s) -> frequency_offset_hz

        Returns:
            PassTxReport summarizing the transmission session
        """
        report = PassTxReport(
            satellite_name=satellite_name,
            pass_start=datetime.now(timezone.utc).isoformat(),
            pass_end="",
            duration_s=pass_duration_s,
        )

        start_time = time.time()
        deadline = start_time + pass_duration_s

        logger.info(
            f"Pass TX started: {satellite_name}, "
            f"window={pass_duration_s:.0f}s, "
            f"duty budget={self.duty_cycle.remaining_s():.1f}s"
        )

        # Pull pending bundles sorted by priority (SOS=0 first)
        bundles = self.bundle_source.get_pending(limit=100)
        if not bundles:
            report.stop_reason = "no_pending_bundles"
            report.pass_end = datetime.now(timezone.utc).isoformat()
            logger.info("No pending bundles to transmit")
            return report

        logger.info(f"Transmitting {len(bundles)} pending bundles")

        for bundle in bundles:
            elapsed = time.time() - start_time

            # Check pass window
            if time.time() >= deadline:
                report.stop_reason = "pass_ended"
                logger.info("Pass window expired")
                break

            # Estimate airtime for this packet
            packet_data = bundle.packet.serialize() if hasattr(bundle.packet, 'serialize') else bundle.packet
            if isinstance(packet_data, bytes):
                payload_size = min(len(packet_data), self.max_payload_bytes)
            else:
                payload_size = self.max_payload_bytes

            airtime = estimate_packet_airtime_s(payload_size)

            # Check duty cycle
            if not self.duty_cycle.can_transmit(airtime):
                report.stop_reason = "duty_cycle_exceeded"
                logger.warning(
                    f"Duty cycle budget exhausted: "
                    f"{self.duty_cycle.used_airtime_s():.1f}s / "
                    f"{self.duty_cycle.budget_s:.1f}s"
                )
                break

            # Compute Doppler offset
            freq_offset = 0.0
            if doppler_offset_fn is not None:
                freq_offset = doppler_offset_fn(elapsed)

            # Transmit
            report.packets_attempted += 1
            try:
                if isinstance(packet_data, bytes):
                    tx_data = packet_data[:self.max_payload_bytes]
                else:
                    tx_data = bytes(self.max_payload_bytes)

                result = await self.tx_driver.transmit(tx_data, freq_offset)

                if result.status == TxStatus.SUCCESS:
                    report.packets_sent += 1
                    actual_airtime = result.airtime_ms / 1000.0 if result.airtime_ms > 0 else airtime
                    report.total_airtime_ms += actual_airtime * 1000
                    self.duty_cycle.record_tx(actual_airtime)
                    self.bundle_source.mark_transmitted(bundle.bundle_id)
                    logger.debug(
                        f"TX OK: bundle={bundle.bundle_id[:8]}... "
                        f"size={payload_size}B airtime={actual_airtime*1000:.0f}ms "
                        f"doppler={freq_offset:+.0f}Hz"
                    )
                else:
                    report.packets_failed += 1
                    self.bundle_source.increment_retry(bundle.bundle_id)
                    logger.warning(f"TX FAIL: bundle={bundle.bundle_id[:8]}... status={result.status.name}")

            except Exception as e:
                report.packets_failed += 1
                self.bundle_source.increment_retry(bundle.bundle_id)
                logger.error(f"TX ERROR: {e}")

            # Inter-packet gap
            await asyncio.sleep(self.inter_packet_gap_ms / 1000.0)

        if not report.stop_reason:
            report.stop_reason = "all_bundles_sent"

        report.pass_end = datetime.now(timezone.utc).isoformat()
        report.duty_cycle_used_pct = self.duty_cycle.utilization_pct()

        logger.info(
            f"Pass TX complete: sent={report.packets_sent}/{report.packets_attempted} "
            f"airtime={report.total_airtime_ms:.0f}ms "
            f"duty={report.duty_cycle_used_pct:.1f}% "
            f"reason={report.stop_reason}"
        )

        return report
