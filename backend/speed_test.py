"""
OpenOrbitLink — Speed Test & Network Statistics Engine

Starlink-inspired features:
1. Built-in speed test (like Starlink app's dish-level speed test)
2. Real-time connectivity statistics with history
3. Obstruction/sky visibility analysis
4. Pass quality scoring and prediction
5. Network health monitoring

Unlike Starlink which tests internet throughput, we measure:
- LoRa link quality (RSSI, SNR, PER)
- Effective throughput per pass
- Compression efficiency
- Queue drain rate
"""

import time
import math
import random
import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from enum import Enum
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LinkQuality(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    NO_LINK = "NO_LINK"


@dataclass
class SpeedTestResult:
    """Result of a link speed test."""
    timestamp: str
    test_duration_s: float
    spreading_factor: int
    bandwidth_hz: int
    raw_bitrate_bps: float
    effective_bitrate_bps: float  # after compression
    packets_sent: int
    packets_received: int
    packet_loss_percent: float
    avg_rssi_dbm: float
    avg_snr_db: float
    avg_airtime_ms: float
    link_quality: str
    compression_ratio: float
    latency_estimate_s: float  # store-and-forward latency
    throughput_bytes_per_pass: int


@dataclass
class NetworkSnapshot:
    """Point-in-time network health snapshot."""
    timestamp: str
    uptime_hours: float
    total_tx_packets: int
    total_rx_packets: int
    total_tx_bytes: int
    total_rx_bytes: int
    current_sf: int
    current_bitrate_bps: float
    adaptive_mode: bool
    queue_depth: int
    queue_bytes: int
    compression_savings_percent: float
    active_satellites: int
    connected_satellite: Optional[str]
    last_contact_ago_s: float
    next_pass_in_s: float
    link_quality: str
    duty_cycle_used_percent: float
    duty_cycle_remaining_s: float


class NetworkStatsEngine:
    """Collects and serves real-time network statistics."""

    def __init__(self, history_size: int = 1000):
        self._start_time = time.time()
        self._tx_packets = 0
        self._rx_packets = 0
        self._tx_bytes = 0
        self._rx_bytes = 0
        self._tx_failures = 0
        self._rssi_history: deque = deque(maxlen=history_size)
        self._snr_history: deque = deque(maxlen=history_size)
        self._throughput_history: deque = deque(maxlen=history_size)
        self._pass_history: list = []
        self._speed_test_results: list = []
        self._current_sf = 12
        self._queue_depth = 0
        self._queue_bytes = 0
        self._connected_sat: Optional[str] = None
        self._last_contact = 0.0
        self._duty_cycle_used_s = 0.0

    def record_tx(self, payload_size: int, airtime_ms: float, sf: int):
        """Record a transmission."""
        self._tx_packets += 1
        self._tx_bytes += payload_size
        self._current_sf = sf
        self._duty_cycle_used_s += airtime_ms / 1000
        self._throughput_history.append({
            "time": datetime.utcnow().isoformat(),
            "bytes": payload_size,
            "airtime_ms": airtime_ms,
            "sf": sf,
            "direction": "TX",
        })

    def record_rx(self, payload_size: int, rssi: float, snr: float):
        """Record a reception."""
        self._rx_packets += 1
        self._rx_bytes += payload_size
        self._rssi_history.append(rssi)
        self._snr_history.append(snr)
        self._last_contact = time.time()
        self._throughput_history.append({
            "time": datetime.utcnow().isoformat(),
            "bytes": payload_size,
            "rssi": rssi,
            "snr": snr,
            "direction": "RX",
        })

    def record_failure(self):
        self._tx_failures += 1

    def set_connected(self, sat_name: Optional[str]):
        self._connected_sat = sat_name

    def set_queue(self, depth: int, total_bytes: int):
        self._queue_depth = depth
        self._queue_bytes = total_bytes

    def classify_link(self, snr: float) -> LinkQuality:
        if snr >= 10:
            return LinkQuality.EXCELLENT
        elif snr >= 5:
            return LinkQuality.GOOD
        elif snr >= 0:
            return LinkQuality.FAIR
        elif snr >= -5:
            return LinkQuality.POOR
        return LinkQuality.NO_LINK

    async def run_speed_test(self, sf: int = 12, bw: int = 125000,
                              num_packets: int = 10, payload_size: int = 80) -> SpeedTestResult:
        """Simulate a speed test (measures theoretical throughput)."""
        start = time.time()

        # Calculate raw bitrate
        raw_bitrate = sf * bw / (2 ** sf)

        # Simulate packet transmission
        t_sym = (2 ** sf) / bw
        n_preamble = (8 + 4.25) * t_sym
        cr = 5
        de = 1 if sf >= 11 else 0
        numerator = 8 * payload_size - 4 * sf + 28 + 16
        denominator = 4 * (sf - 2 * de)
        n_payload = 8 + max(0, math.ceil(numerator / denominator)) * cr if denominator > 0 else 8
        airtime_ms = (n_preamble + n_payload * t_sym) * 1000

        # Simulate success/failure
        success_rate = 0.95 if sf >= 10 else 0.85
        successes = sum(1 for _ in range(num_packets) if random.random() < success_rate)
        failures = num_packets - successes

        # Compression bonus (typical 20-40%)
        compression_ratio = 0.72

        duration = time.time() - start + (airtime_ms * num_packets / 1000)

        avg_rssi = -130 + (12 - sf) * 2 + random.gauss(0, 2)
        avg_snr = -20 + (12 - sf) * 3 + random.gauss(0, 1.5)

        effective_bps = raw_bitrate / compression_ratio
        bytes_per_pass = int(effective_bps * 420 / 8 * 0.01)  # 1% duty

        result = SpeedTestResult(
            timestamp=datetime.utcnow().isoformat(),
            test_duration_s=round(duration, 2),
            spreading_factor=sf,
            bandwidth_hz=bw,
            raw_bitrate_bps=round(raw_bitrate, 1),
            effective_bitrate_bps=round(effective_bps, 1),
            packets_sent=num_packets,
            packets_received=successes,
            packet_loss_percent=round(failures / num_packets * 100, 1),
            avg_rssi_dbm=round(avg_rssi, 1),
            avg_snr_db=round(avg_snr, 1),
            avg_airtime_ms=round(airtime_ms, 1),
            link_quality=self.classify_link(avg_snr).value,
            compression_ratio=compression_ratio,
            latency_estimate_s=round(random.uniform(300, 5400), 0),
            throughput_bytes_per_pass=bytes_per_pass,
        )
        self._speed_test_results.append(result)
        return result

    def get_snapshot(self) -> NetworkSnapshot:
        """Get current network health snapshot."""
        uptime = (time.time() - self._start_time) / 3600
        avg_snr = sum(self._snr_history) / len(self._snr_history) if self._snr_history else -20
        last_contact_ago = time.time() - self._last_contact if self._last_contact > 0 else 99999

        sf_bitrates = {7: 5469, 8: 3125, 9: 1758, 10: 977, 11: 537, 12: 293}
        current_bps = sf_bitrates.get(self._current_sf, 293)

        # Simulated next pass
        next_pass = random.uniform(600, 5400)

        return NetworkSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            uptime_hours=round(uptime, 2),
            total_tx_packets=self._tx_packets,
            total_rx_packets=self._rx_packets,
            total_tx_bytes=self._tx_bytes,
            total_rx_bytes=self._rx_bytes,
            current_sf=self._current_sf,
            current_bitrate_bps=current_bps,
            adaptive_mode=True,
            queue_depth=self._queue_depth,
            queue_bytes=self._queue_bytes,
            compression_savings_percent=28.0,
            active_satellites=random.randint(2, 5),
            connected_satellite=self._connected_sat,
            last_contact_ago_s=round(last_contact_ago, 0),
            next_pass_in_s=round(next_pass, 0),
            link_quality=self.classify_link(avg_snr).value,
            duty_cycle_used_percent=round(self._duty_cycle_used_s / 36 * 100, 1),
            duty_cycle_remaining_s=round(max(0, 36 - self._duty_cycle_used_s), 1),
        )

    def get_history(self, last_n: int = 100) -> dict:
        """Get recent history for charts."""
        return {
            "rssi": list(self._rssi_history)[-last_n:],
            "snr": list(self._snr_history)[-last_n:],
            "throughput": list(self._throughput_history)[-last_n:],
            "speed_tests": [
                {
                    "timestamp": r.timestamp,
                    "sf": r.spreading_factor,
                    "raw_bps": r.raw_bitrate_bps,
                    "effective_bps": r.effective_bitrate_bps,
                    "loss_pct": r.packet_loss_percent,
                    "quality": r.link_quality,
                }
                for r in self._speed_test_results[-20:]
            ],
        }


# ---------- Smart Pass Scheduler ----------

@dataclass
class QueuedMessage:
    """Message waiting to be transmitted during next pass."""
    id: str
    data: bytes
    priority: int  # 0=SOS, 1=urgent, 2=normal, 3=bulk
    created_at: float
    compressed_size: int
    destination: str
    retries: int = 0
    max_retries: int = 5


class PassScheduler:
    """Schedules message transmission for optimal satellite passes.

    Starlink-inspired: like Starlink's traffic prioritization,
    we prioritize SOS > urgent > normal > bulk and schedule
    transmissions during highest-elevation (fastest) pass windows.
    """

    def __init__(self):
        self._queue: list[QueuedMessage] = []

    def enqueue(self, msg: QueuedMessage):
        self._queue.append(msg)
        self._queue.sort(key=lambda m: (m.priority, m.created_at))

    def get_transmission_plan(self, pass_duration_s: int = 420,
                                max_elevation_deg: float = 55,
                                duty_cycle_remaining_s: float = 36) -> dict:
        """Create optimal TX plan for upcoming pass."""
        plan = {"slots": [], "total_bytes": 0, "total_airtime_s": 0,
                "messages_scheduled": 0, "messages_deferred": 0}

        airtime_budget = duty_cycle_remaining_s
        scheduled = []
        deferred = []

        for msg in self._queue:
            # Estimate airtime for this message
            sf = self._sf_for_elevation(max_elevation_deg)
            bw = 125000
            t_sym = (2 ** sf) / bw
            airtime_s = t_sym * (8 + 4.25 + max(8, msg.compressed_size // 2)) 

            if plan["total_airtime_s"] + airtime_s <= airtime_budget:
                slot = {
                    "message_id": msg.id,
                    "priority": msg.priority,
                    "size_bytes": msg.compressed_size,
                    "sf": sf,
                    "airtime_s": round(airtime_s, 3),
                    "window": self._best_window(max_elevation_deg, sf),
                }
                plan["slots"].append(slot)
                plan["total_bytes"] += msg.compressed_size
                plan["total_airtime_s"] += airtime_s
                plan["messages_scheduled"] += 1
                scheduled.append(msg)
            else:
                plan["messages_deferred"] += 1
                deferred.append(msg)

        plan["total_airtime_s"] = round(plan["total_airtime_s"], 2)
        plan["duty_cycle_used_percent"] = round(plan["total_airtime_s"] / 36 * 100, 1)
        return plan

    def _sf_for_elevation(self, el: float) -> int:
        if el > 60: return 7
        if el > 45: return 8
        if el > 30: return 9
        if el > 20: return 10
        if el > 10: return 11
        return 12

    def _best_window(self, max_el: float, sf: int) -> str:
        if sf <= 8:
            return "TCA ± 60s (peak elevation)"
        elif sf <= 10:
            return "Mid-pass (120-300s)"
        return "Full pass (any time)"


# ---------- FastAPI Router ----------

speedtest_router = APIRouter(prefix="/api/v1/network", tags=["Network & Speed Test"])
_engine = NetworkStatsEngine()
_scheduler = PassScheduler()


class SpeedTestRequest(BaseModel):
    spreading_factor: int = 12
    num_packets: int = 10
    payload_size: int = 80


@speedtest_router.post("/speed-test")
async def run_speed_test(req: SpeedTestRequest):
    """Run a link speed test (Starlink-style)."""
    result = await _engine.run_speed_test(
        sf=req.spreading_factor,
        num_packets=req.num_packets,
        payload_size=req.payload_size,
    )
    return {
        "timestamp": result.timestamp,
        "spreading_factor": result.spreading_factor,
        "raw_bitrate_bps": result.raw_bitrate_bps,
        "effective_bitrate_bps": result.effective_bitrate_bps,
        "packets": f"{result.packets_received}/{result.packets_sent}",
        "packet_loss": f"{result.packet_loss_percent}%",
        "rssi": f"{result.avg_rssi_dbm} dBm",
        "snr": f"{result.avg_snr_db} dB",
        "airtime": f"{result.avg_airtime_ms} ms",
        "link_quality": result.link_quality,
        "bytes_per_pass": result.throughput_bytes_per_pass,
        "latency_estimate": f"{result.latency_estimate_s}s (store-and-forward)",
    }


@speedtest_router.get("/stats")
async def network_stats():
    """Get real-time network statistics snapshot."""
    return _engine.get_snapshot()


@speedtest_router.get("/history")
async def network_history(last_n: int = 100):
    """Get historical RSSI, SNR, and throughput data for charts."""
    return _engine.get_history(last_n)


@speedtest_router.get("/pass-plan")
async def get_pass_plan(max_elevation: float = 55, duration_s: int = 420):
    """Get optimized transmission plan for next pass."""
    return _scheduler.get_transmission_plan(
        pass_duration_s=duration_s,
        max_elevation_deg=max_elevation,
    )


@speedtest_router.get("/health")
async def network_health():
    """Quick health check with traffic-light status."""
    snap = _engine.get_snapshot()
    return {
        "status": snap.link_quality,
        "uptime_hours": snap.uptime_hours,
        "tx_packets": snap.total_tx_packets,
        "rx_packets": snap.total_rx_packets,
        "queue_depth": snap.queue_depth,
        "duty_cycle_remaining_s": snap.duty_cycle_remaining_s,
        "next_pass_in_s": snap.next_pass_in_s,
        "connected": snap.connected_satellite,
    }
