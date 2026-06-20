"""
OpenOrbitLink LR-FHSS Engine — Frequency Hopping for Satellite IoT

Implements LR-FHSS packet generation, hopping sequence computation,
and capacity analysis based on Semtech AN1200.64 specification.

LR-FHSS advantages over standard LoRa:
- 100-140x network capacity improvement
- ±3,900 Hz Doppler tolerance (vs ±1,500 Hz for SF12)
- Bypasses EU 1% duty cycle (classified as FHSS)
- Larger payloads: 125 bytes vs 80 bytes
- Better interference robustness via frequency diversity

Capacity comparison:
    ┌──────────────────────┬────────────┬──────────────┬──────────────┐
    │ Parameter            │ LoRa SF12  │ LR-FHSS CR1/3│ LR-FHSS CR2/3│
    ├──────────────────────┼────────────┼──────────────┼──────────────┤
    │ Bitrate              │ 293 bps    │ 162 bps      │ 325 bps      │
    │ Sensitivity          │ -137 dBm   │ -142 dBm     │ -139 dBm     │
    │ Doppler tolerance    │ ±1,500 Hz  │ ±3,900 Hz    │ ±3,900 Hz    │
    │ Max payload          │ 80 bytes   │ 125 bytes    │ 125 bytes    │
    │ Duty cycle bypass    │ No (1%)    │ Yes (FHSS)   │ Yes (FHSS)   │
    │ Devices/satellite    │ ~15        │ ~1,500       │ ~2,000       │
    │ Bytes/hour (1 device)│ 960        │ ~7,500       │ ~7,500       │
    └──────────────────────┴────────────┴──────────────┴──────────────┘
"""

from __future__ import annotations

import math
import logging
import struct
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("OpenOrbitLink.LR_FHSS")


# ── LR-FHSS Configuration ───────────────────────────────────────────

@dataclass
class LRFHSSConfig:
    """LR-FHSS radio configuration parameters."""
    coding_rate: int = 1          # 1 = CR 1/3 (most robust), 2 = CR 2/3
    grid: str = "narrow"          # "narrow" (3.9 kHz steps) or "wide" (25.39 kHz)
    bandwidth_hz: int = 137_000   # 137 kHz or 336 kHz operating channel width
    nb_hops: int = 35             # Number of frequency hops per packet
    header_count: int = 3         # Header replicas for robustness (1-4)
    carrier_freq_hz: int = 868_000_000  # Center frequency
    max_payload: int = 125        # Maximum payload bytes
    hop_duration_ms: float = 4.096  # Duration of each hop (1 LoRa symbol at SF12/BW125)

    @property
    def grid_step_hz(self) -> float:
        """Frequency step between hopping channels."""
        return 3_906.25 if self.grid == "narrow" else 25_390.625

    @property
    def grid_count(self) -> int:
        """Number of available hopping channels."""
        return int(self.bandwidth_hz / self.grid_step_hz)

    @property
    def bitrate_bps(self) -> float:
        """Effective data bitrate."""
        return 162 if self.coding_rate == 1 else 325

    @property
    def sensitivity_dbm(self) -> float:
        """Receiver sensitivity."""
        return -142.0 if self.coding_rate == 1 else -139.0

    @property
    def doppler_tolerance_hz(self) -> float:
        """Maximum tolerable Doppler shift."""
        return 3_900.0


# ── Hopping Sequence Generator ───────────────────────────────────────

class HoppingSequence:
    """Generates pseudo-random frequency hopping sequences for LR-FHSS."""

    @staticmethod
    def generate(seed: int, nb_hops: int, grid_count: int) -> list[int]:
        """Generate a PRNG-based hopping sequence.

        Uses XOR shift PRNG seeded with device-specific value to ensure
        unique hopping patterns across devices (minimizes collision).

        Args:
            seed: Device-specific seed (e.g., DevAddr hash)
            nb_hops: Number of hops in the sequence
            grid_count: Total available frequency channels

        Returns:
            List of channel indices for each hop
        """
        channels = []
        state = seed if seed != 0 else 0xACE1
        for _ in range(nb_hops):
            # XOR shift 16-bit PRNG
            state ^= (state << 7) & 0xFFFF
            state ^= (state >> 9) & 0xFFFF
            state ^= (state << 8) & 0xFFFF
            state &= 0xFFFF
            channel = state % grid_count
            channels.append(channel)
        return channels

    @staticmethod
    def channels_to_frequencies(channels: list[int], center_freq: int,
                                 grid_step: float) -> list[float]:
        """Convert channel indices to actual frequencies in Hz."""
        n = len(channels)
        half = n // 2
        return [center_freq + (ch - half) * grid_step for ch in channels]

    @staticmethod
    def visualize(channels: list[int], grid_count: int, width: int = 50) -> str:
        """Generate text-based frequency-time diagram."""
        lines = ["LR-FHSS Hopping Pattern:", f"{'Time':>6} | {'Frequency Channel':^{width}} |"]
        lines.append("-" * (width + 10))
        for i, ch in enumerate(channels[:20]):  # Show first 20 hops
            pos = int(ch / grid_count * width)
            bar = "." * pos + "█" + "." * (width - pos - 1)
            lines.append(f"  {i:3d}  | {bar} | ch={ch}")
        if len(channels) > 20:
            lines.append(f"  ... ({len(channels) - 20} more hops)")
        return "\n".join(lines)


# ── LR-FHSS Packet ──────────────────────────────────────────────────

@dataclass
class LRFHSSFragment:
    """A single fragment of an LR-FHSS packet."""
    index: int
    data: bytes
    frequency_hz: float
    hop_index: int
    is_header: bool = False


class LRFHSSPacket:
    """LR-FHSS packet fragmentation and airtime estimation."""

    @staticmethod
    def fragment(payload: bytes, config: LRFHSSConfig,
                 seed: int = 42) -> list[LRFHSSFragment]:
        """Fragment payload into hopping packet pieces.

        LR-FHSS splits the payload into small fragments, each transmitted
        on a different frequency. Header is replicated for robustness.
        """
        # Generate hopping sequence
        channels = HoppingSequence.generate(seed, config.nb_hops, config.grid_count)
        frequencies = HoppingSequence.channels_to_frequencies(
            channels, config.carrier_freq_hz, config.grid_step_hz
        )

        fragments = []

        # Header fragments (replicated for robustness)
        header_data = struct.pack("<HBB", len(payload), config.coding_rate, config.nb_hops)
        for i in range(config.header_count):
            fragments.append(LRFHSSFragment(
                index=i, data=header_data,
                frequency_hz=frequencies[i], hop_index=i, is_header=True
            ))

        # Data fragments
        # Compute fragment size based on coding rate
        raw_bits_per_hop = 48 if config.coding_rate == 1 else 96  # bits
        bytes_per_hop = raw_bits_per_hop // 8

        offset = 0
        hop_idx = config.header_count
        frag_idx = 0

        while offset < len(payload) and hop_idx < len(frequencies):
            chunk = payload[offset:offset + bytes_per_hop]
            fragments.append(LRFHSSFragment(
                index=frag_idx + config.header_count,
                data=chunk,
                frequency_hz=frequencies[hop_idx],
                hop_index=hop_idx,
                is_header=False,
            ))
            offset += bytes_per_hop
            hop_idx += 1
            frag_idx += 1

        return fragments

    @staticmethod
    def estimate_airtime(payload_size: int, config: LRFHSSConfig) -> float:
        """Estimate total airtime for LR-FHSS packet in milliseconds."""
        # Header time
        header_time = config.header_count * config.hop_duration_ms

        # Data hops needed
        bytes_per_hop = 6 if config.coding_rate == 1 else 12
        data_hops = math.ceil(payload_size / bytes_per_hop)

        data_time = data_hops * config.hop_duration_ms

        # Guard intervals between hops
        guard_time = (config.header_count + data_hops) * 0.233  # ms

        return header_time + data_time + guard_time

    @staticmethod
    def capacity_vs_lora(config: LRFHSSConfig) -> dict:
        """Compare LR-FHSS capacity with standard LoRa SF12."""
        # LoRa SF12/BW125 baseline
        lora_airtime_ms = 2867.5  # 80 bytes
        lora_packets_hr = int(36_000 / lora_airtime_ms)  # 12
        lora_bytes_hr = lora_packets_hr * 80  # 960

        # LR-FHSS
        fhss_airtime_ms = LRFHSSPacket.estimate_airtime(125, config)
        # FHSS bypasses duty cycle — use 10% effective duty
        fhss_budget_ms = 360_000  # 10% of 1 hour
        fhss_packets_hr = int(fhss_budget_ms / fhss_airtime_ms)
        fhss_bytes_hr = fhss_packets_hr * 125

        return {
            "lora_sf12": {
                "bitrate_bps": 293,
                "sensitivity_dbm": -137,
                "max_payload": 80,
                "airtime_80b_ms": lora_airtime_ms,
                "packets_per_hour": lora_packets_hr,
                "bytes_per_hour": lora_bytes_hr,
                "duty_cycle_pct": 1.0,
                "doppler_tolerance_hz": 1500,
                "devices_per_sat": 15,
            },
            "lr_fhss": {
                "coding_rate": f"CR {config.coding_rate}/3",
                "bitrate_bps": config.bitrate_bps,
                "sensitivity_dbm": config.sensitivity_dbm,
                "max_payload": config.max_payload,
                "airtime_125b_ms": round(fhss_airtime_ms, 1),
                "packets_per_hour": fhss_packets_hr,
                "bytes_per_hour": fhss_bytes_hr,
                "duty_cycle_pct": 10.0,
                "doppler_tolerance_hz": config.doppler_tolerance_hz,
                "devices_per_sat": config.grid_count * 50,
            },
            "improvement": {
                "capacity_multiplier": round(fhss_bytes_hr / max(1, lora_bytes_hr), 1),
                "devices_multiplier": round(config.grid_count * 50 / 15, 1),
                "doppler_improvement": round(config.doppler_tolerance_hz / 1500, 1),
                "payload_improvement": round(125 / 80, 2),
            },
        }


# ── Capacity Analyzer ────────────────────────────────────────────────

class LRFHSSCapacityAnalyzer:
    """Analyzes LR-FHSS network capacity for satellite IoT."""

    def __init__(self, config: Optional[LRFHSSConfig] = None):
        self.config = config or LRFHSSConfig()

    def devices_per_satellite(self, footprint_km: float = 5000) -> int:
        """Estimate devices supportable within satellite footprint."""
        n_channels = self.config.grid_count
        # Each channel can support ~50 devices with 1% collision rate
        return n_channels * 50

    def throughput_per_device(self) -> dict:
        """Calculate per-device throughput."""
        airtime = LRFHSSPacket.estimate_airtime(125, self.config)
        # With FHSS duty cycle bypass: 10% effective
        budget_ms = 360_000
        packets = int(budget_ms / airtime)
        bytes_hr = packets * 125

        return {
            "packets_per_hour": packets,
            "bytes_per_hour": bytes_hr,
            "bits_per_second_avg": round(bytes_hr * 8 / 3600, 1),
            "messages_per_day": packets * 24,
        }

    def collision_probability(self, n_devices: int, n_channels: int = 0,
                               packet_duration_ms: float = 0) -> float:
        """Estimate packet collision probability (ALOHA-like model)."""
        if n_channels == 0:
            n_channels = self.config.grid_count
        if packet_duration_ms == 0:
            packet_duration_ms = LRFHSSPacket.estimate_airtime(125, self.config)

        # Channel utilization per device
        packets_per_sec = 1 / 30  # 1 packet every 30 seconds average
        duty_per_channel = (packets_per_sec * packet_duration_ms / 1000) / n_channels

        # Total channel utilization
        total_util = n_devices * duty_per_channel

        # ALOHA collision: P_collision = 1 - e^(-2G)
        p_collision = 1 - math.exp(-2 * total_util)
        return min(p_collision, 1.0)

    def compare_with_lora_sf12(self) -> dict:
        """Full comparison between LR-FHSS and LoRa SF12."""
        return LRFHSSPacket.capacity_vs_lora(self.config)


# ── FastAPI Router ───────────────────────────────────────────────────

try:
    from fastapi import APIRouter, Query
    router = APIRouter(prefix="/api/v1/lr-fhss", tags=["lr-fhss"])

    _config = LRFHSSConfig()
    _analyzer = LRFHSSCapacityAnalyzer(_config)

    @router.get("/config")
    async def get_config():
        """Get current LR-FHSS configuration."""
        return {
            "coding_rate": f"CR {_config.coding_rate}/3",
            "grid": _config.grid,
            "grid_step_hz": _config.grid_step_hz,
            "grid_channels": _config.grid_count,
            "bandwidth_hz": _config.bandwidth_hz,
            "nb_hops": _config.nb_hops,
            "header_replicas": _config.header_count,
            "carrier_freq_hz": _config.carrier_freq_hz,
            "max_payload_bytes": _config.max_payload,
            "bitrate_bps": _config.bitrate_bps,
            "sensitivity_dbm": _config.sensitivity_dbm,
            "doppler_tolerance_hz": _config.doppler_tolerance_hz,
        }

    @router.get("/hopping-sequence")
    async def hopping_sequence(
        seed: int = Query(42, description="Device seed"),
        hops: int = Query(35, description="Number of hops"),
    ):
        """Generate a frequency hopping sequence."""
        channels = HoppingSequence.generate(seed, hops, _config.grid_count)
        frequencies = HoppingSequence.channels_to_frequencies(
            channels, _config.carrier_freq_hz, _config.grid_step_hz
        )
        diagram = HoppingSequence.visualize(channels, _config.grid_count)

        return {
            "seed": seed,
            "nb_hops": hops,
            "grid_channels": _config.grid_count,
            "channels": channels,
            "frequencies_hz": [round(f, 2) for f in frequencies],
            "diagram": diagram,
        }

    @router.get("/capacity")
    async def capacity_analysis():
        """Compare LR-FHSS capacity with standard LoRa."""
        comparison = _analyzer.compare_with_lora_sf12()
        throughput = _analyzer.throughput_per_device()
        devices = _analyzer.devices_per_satellite()

        return {
            **comparison,
            "per_device": throughput,
            "max_devices_per_satellite": devices,
        }

    @router.get("/simulate")
    async def simulate(
        payload_size: int = Query(80, description="Payload in bytes"),
        n_devices: int = Query(100, description="Number of devices"),
    ):
        """Simulate LR-FHSS capacity for N devices."""
        airtime = LRFHSSPacket.estimate_airtime(payload_size, _config)
        collision_prob = _analyzer.collision_probability(n_devices)
        effective_throughput = (1 - collision_prob)

        return {
            "payload_size": payload_size,
            "n_devices": n_devices,
            "airtime_ms": round(airtime, 1),
            "collision_probability": round(collision_prob, 4),
            "effective_delivery_rate": round(effective_throughput, 4),
            "total_network_bytes_per_hour": int(
                n_devices * _analyzer.throughput_per_device()["bytes_per_hour"]
                * effective_throughput
            ),
            "grid_channels": _config.grid_count,
            "hopping_diversity": _config.nb_hops,
        }

except ImportError:
    router = None
    logger.info("FastAPI not available, LR-FHSS API disabled")
