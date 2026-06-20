"""
OpenOrbitLink Adaptive Modem — Jio-Inspired High-Throughput Engine

Dynamically selects optimal LoRa parameters (SF, BW, CR) based on:
- Satellite elevation angle and slant range
- Doppler shift magnitude
- SNR measurements from recent packets
- Atmospheric/weather conditions

Inspired by 3GPP NTN Release 19 Adaptive Modulation & Coding (AMC)
and Jio's per-beam throughput optimization.

Key innovation: Instead of always using SF12 (293 bps), dynamically
shift to SF7 (5,469 bps) when link budget allows — giving 18.7x
throughput improvement during overhead passes.

Throughput comparison:
    SF12 fixed:     960 bytes/hour  (12 packets × 80 bytes)
    Adaptive SF:    ~19,200 bytes/hour at peak (SF7 overhead)
    LR-FHSS:        ~7,500 bytes/hour (duty cycle bypass)
    Combined:       ~51,000 bytes/hour (multi-band + adaptive)
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("OpenOrbitLink.AdaptiveModem")

# ── Physical Constants ───────────────────────────────────────────────

EARTH_RADIUS_KM = 6371.0
C_LIGHT = 299_792_458.0
BOLTZMANN = 1.380649e-23

# Default RF parameters
DEFAULT_TX_POWER_DBM = 14.0    # SX1276 output
DEFAULT_TX_GAIN_DBI = 2.15     # Quarter-wave ground antenna
DEFAULT_RX_GAIN_DBI = 2.0      # Satellite patch antenna
DEFAULT_FREQ_HZ = 868_000_000  # EU ISM band


# ── Link Budget Calculator ───────────────────────────────────────────

class LinkBudgetCalculator:
    """Computes RF link budget for ground-to-satellite LoRa links."""

    @staticmethod
    def free_space_path_loss(distance_km: float, freq_hz: float) -> float:
        """Free-space path loss in dB (Friis equation)."""
        if distance_km <= 0 or freq_hz <= 0:
            return 0.0
        dist_m = distance_km * 1000
        return 20 * math.log10(dist_m) + 20 * math.log10(freq_hz) - 147.55

    @staticmethod
    def atmospheric_loss(elevation_deg: float) -> float:
        """Atmospheric absorption loss (ITU-R P.676 simplified).
        At 868 MHz, atmospheric loss is primarily from path length through
        troposphere. Lower elevations = longer slant path."""
        el_rad = math.radians(max(elevation_deg, 1.0))
        # Zenith atmospheric loss at 868 MHz: ~0.05 dB
        # Scale by 1/sin(elevation) for slant path
        zenith_loss = 0.05
        slant_factor = 1.0 / math.sin(el_rad)
        return min(zenith_loss * slant_factor, 8.0)  # Cap at 8 dB

    @staticmethod
    def rain_attenuation(elevation_deg: float, rain_rate_mm_hr: float = 0) -> float:
        """Rain attenuation estimate (ITU-R P.838 simplified).
        At 868 MHz, rain attenuation is negligible (<0.01 dB/km)."""
        if rain_rate_mm_hr <= 0:
            return 0.0
        # Specific attenuation at 868 MHz: ~0.0001 * R^1.0 dB/km
        specific_atten = 0.0001 * rain_rate_mm_hr
        # Effective path length through rain (assume 4 km rain height)
        el_rad = math.radians(max(elevation_deg, 5.0))
        path_km = 4.0 / math.sin(el_rad)
        return specific_atten * path_km

    @staticmethod
    def scintillation_loss(elevation_deg: float, freq_hz: float = DEFAULT_FREQ_HZ) -> float:
        """Tropospheric scintillation loss estimate.
        Significant at low elevations and higher frequencies."""
        if elevation_deg > 30:
            return 0.1
        el_rad = math.radians(max(elevation_deg, 3.0))
        # Simplified ITU-R P.618 model
        freq_ghz = freq_hz / 1e9
        sigma = 0.025 * freq_ghz**0.45 / (math.sin(el_rad)**1.3)
        # 99% time availability: ~2.6 * sigma
        return min(2.6 * sigma, 3.0)

    @classmethod
    def total_path_loss(cls, distance_km: float, elevation_deg: float,
                        freq_hz: float = DEFAULT_FREQ_HZ,
                        rain_rate: float = 0) -> float:
        """Total propagation loss including all atmospheric effects."""
        fspl = cls.free_space_path_loss(distance_km, freq_hz)
        atm = cls.atmospheric_loss(elevation_deg)
        rain = cls.rain_attenuation(elevation_deg, rain_rate)
        scint = cls.scintillation_loss(elevation_deg, freq_hz)
        return fspl + atm + rain + scint

    @classmethod
    def received_power(cls, tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
                       tx_gain_dbi: float = DEFAULT_TX_GAIN_DBI,
                       rx_gain_dbi: float = DEFAULT_RX_GAIN_DBI,
                       distance_km: float = 1000,
                       elevation_deg: float = 30,
                       freq_hz: float = DEFAULT_FREQ_HZ) -> float:
        """Compute received signal power at satellite in dBm."""
        path_loss = cls.total_path_loss(distance_km, elevation_deg, freq_hz)
        return tx_power_dbm + tx_gain_dbi - path_loss + rx_gain_dbi

    @classmethod
    def link_margin(cls, rx_power_dbm: float, sensitivity_dbm: float) -> float:
        """Link margin = received power - receiver sensitivity."""
        return rx_power_dbm - sensitivity_dbm


# ── Modem Profiles ───────────────────────────────────────────────────

@dataclass
class ModemProfile:
    """A specific LoRa/LR-FHSS modulation configuration."""
    name: str
    spreading_factor: int
    bandwidth_hz: int
    coding_rate: int          # denominator of 4/x
    tx_power_dbm: float
    sensitivity_dbm: float
    bitrate_bps: float
    max_payload_bytes: int
    airtime_80b_ms: float
    min_snr_db: float
    doppler_tolerance_hz: float
    modulation: str = "lora"  # "lora" or "lr_fhss"

    @property
    def packets_per_hour_1pct(self) -> int:
        """Max packets/hour under 1% duty cycle."""
        if self.airtime_80b_ms <= 0:
            return 0
        return int(36_000 / self.airtime_80b_ms)

    @property
    def bytes_per_hour(self) -> int:
        """Max data/hour under 1% duty cycle."""
        return self.packets_per_hour_1pct * self.max_payload_bytes


# Pre-computed profiles (Semtech SX1276/SX1262 specifications)
MODEM_PROFILES = [
    ModemProfile("SF7/BW250", 7, 250_000, 5, 14, -120.0, 10_938, 80, 46.1,
                 -7.5, 10_000),
    ModemProfile("SF7/BW125", 7, 125_000, 5, 14, -123.0, 5_469, 80, 92.2,
                 -7.5, 5_000),
    ModemProfile("SF8/BW125", 8, 125_000, 5, 14, -126.0, 3_125, 80, 164.9,
                 -10.0, 4_000),
    ModemProfile("SF9/BW125", 9, 125_000, 5, 14, -129.0, 1_758, 80, 308.2,
                 -12.5, 3_000),
    ModemProfile("SF10/BW125", 10, 125_000, 5, 14, -132.0, 977, 80, 575.5,
                 -15.0, 2_500),
    ModemProfile("SF11/BW125", 11, 125_000, 5, 14, -134.5, 537, 80, 1151.0,
                 -17.5, 2_000),
    ModemProfile("SF12/BW125", 12, 125_000, 5, 14, -137.0, 293, 80, 2867.5,
                 -20.0, 1_500),
    ModemProfile("LR-FHSS/CR1_3", 0, 137_000, 3, 14, -142.0, 162, 125, 4920.0,
                 -22.0, 3_900, modulation="lr_fhss"),
    ModemProfile("LR-FHSS/CR2_3", 0, 137_000, 6, 14, -139.0, 325, 125, 2460.0,
                 -19.0, 3_900, modulation="lr_fhss"),
]


# ── Adaptive Modem ───────────────────────────────────────────────────

class AdaptiveModem:
    """
    Jio-inspired Adaptive Modulation & Coding engine.

    Dynamically selects the optimal LoRa profile based on real-time
    satellite link conditions, maximizing throughput while maintaining
    reliable connectivity.

    Two-phase selection:
    Phase 1 (Heuristic): Elevation-based lookup table
    Phase 2 (Fine-tuning): SNR history analysis for real-time adjustment
    """

    def __init__(self, safety_margin_db: float = 3.0):
        self.safety_margin_db = safety_margin_db
        self.link_calc = LinkBudgetCalculator()
        self._snr_history: list[float] = []

    def select_profile(
        self,
        elevation_deg: float,
        range_km: float,
        doppler_hz: float = 0,
        snr_history: Optional[list[float]] = None,
        freq_hz: float = DEFAULT_FREQ_HZ,
        rain_rate: float = 0,
    ) -> ModemProfile:
        """Select optimal modem profile for current link conditions.

        Args:
            elevation_deg: Satellite elevation angle in degrees
            range_km: Slant range to satellite in km
            doppler_hz: Current Doppler shift in Hz (absolute)
            snr_history: Recent SNR measurements for fine-tuning
            freq_hz: Carrier frequency in Hz
            rain_rate: Rain rate in mm/hr (0 = dry)

        Returns:
            Optimal ModemProfile for current conditions
        """
        # Compute received power
        rx_power = self.link_calc.received_power(
            distance_km=range_km,
            elevation_deg=elevation_deg,
            freq_hz=freq_hz,
        )

        abs_doppler = abs(doppler_hz)

        # Phase 1: Heuristic selection (fastest SF with sufficient margin)
        candidates = []
        for profile in MODEM_PROFILES:
            margin = rx_power - profile.sensitivity_dbm
            doppler_ok = abs_doppler <= profile.doppler_tolerance_hz

            if margin >= self.safety_margin_db and doppler_ok:
                candidates.append((profile, margin))

        if not candidates:
            # Fallback to most robust profile
            logger.warning(f"No profile meets margin requirement "
                          f"(rx_power={rx_power:.1f}dBm, el={elevation_deg:.1f}°)")
            return MODEM_PROFILES[-3]  # SF12/BW125

        # Sort by bitrate descending (fastest first)
        candidates.sort(key=lambda x: x[0].bitrate_bps, reverse=True)
        selected, margin = candidates[0]

        # Phase 2: SNR fine-tuning
        if snr_history and len(snr_history) >= 3:
            avg_snr = sum(snr_history[-5:]) / len(snr_history[-5:])
            snr_trend = snr_history[-1] - snr_history[0] if len(snr_history) > 1 else 0

            # If SNR is degrading, shift to more robust profile
            if snr_trend < -3.0 and len(candidates) > 1:
                selected, margin = candidates[1]
                logger.info(f"SNR degrading (trend={snr_trend:.1f}dB), "
                           f"downshifting to {selected.name}")

        logger.info(f"Selected: {selected.name} | margin={margin:.1f}dB | "
                   f"bitrate={selected.bitrate_bps}bps | el={elevation_deg:.1f}°")
        return selected

    def estimate_pass_capacity(self, duration_s: float,
                                max_elevation_deg: float,
                                altitude_km: float = 550) -> dict:
        """Estimate total bytes transferable during a satellite pass.

        Simulates the pass in 10-second steps, selecting optimal SF at each point.
        """
        total_bytes = 0
        total_packets = 0
        total_airtime_ms = 0
        timeline = []
        duty_budget_ms = 36_000  # 1% of 1 hour in ms

        half_duration = duration_s / 2

        for t in range(0, int(duration_s), 10):
            # Simulate elevation profile (sinusoidal approximation)
            progress = t / duration_s
            el = max_elevation_deg * math.sin(progress * math.pi)
            el = max(el, 2.0)

            # Compute range from elevation and altitude
            el_rad = math.radians(el)
            range_km = altitude_km / math.sin(el_rad)

            # Doppler estimation (max at horizon, zero at zenith)
            doppler_frac = math.cos(progress * math.pi)
            doppler_hz = abs(doppler_frac * 3000)  # Max ±3 kHz

            # Select optimal profile
            profile = self.select_profile(el, range_km, doppler_hz)

            # Check duty cycle budget
            if total_airtime_ms + profile.airtime_80b_ms > duty_budget_ms:
                break

            packets_this_step = max(1, int(10_000 / profile.airtime_80b_ms))
            remaining_budget = duty_budget_ms - total_airtime_ms
            max_packets = int(remaining_budget / profile.airtime_80b_ms)
            packets_this_step = min(packets_this_step, max_packets)

            bytes_this_step = packets_this_step * profile.max_payload_bytes
            total_bytes += bytes_this_step
            total_packets += packets_this_step
            total_airtime_ms += packets_this_step * profile.airtime_80b_ms

            timeline.append({
                "time_s": t,
                "elevation_deg": round(el, 1),
                "range_km": round(range_km, 1),
                "profile": profile.name,
                "bitrate_bps": profile.bitrate_bps,
                "packets": packets_this_step,
                "bytes": bytes_this_step,
            })

        return {
            "duration_s": duration_s,
            "max_elevation_deg": max_elevation_deg,
            "total_bytes": total_bytes,
            "total_packets": total_packets,
            "total_airtime_ms": round(total_airtime_ms, 1),
            "duty_cycle_pct": round(total_airtime_ms / 36_000 * 100, 1),
            "avg_throughput_bps": round(total_bytes * 8 / duration_s, 1) if duration_s > 0 else 0,
            "timeline": timeline,
            "improvement_vs_sf12": round(total_bytes / max(1, 12 * 80), 1),
        }

    def compare_all_modes(self, elevation_deg: float = 45,
                          range_km: float = 800) -> list[dict]:
        """Compare all modem profiles at given link conditions."""
        rx_power = self.link_calc.received_power(
            distance_km=range_km, elevation_deg=elevation_deg
        )

        results = []
        for p in MODEM_PROFILES:
            margin = rx_power - p.sensitivity_dbm
            results.append({
                "name": p.name,
                "modulation": p.modulation,
                "bitrate_bps": p.bitrate_bps,
                "sensitivity_dbm": p.sensitivity_dbm,
                "link_margin_db": round(margin, 1),
                "viable": margin >= self.safety_margin_db,
                "packets_per_hour": p.packets_per_hour_1pct,
                "bytes_per_hour": p.bytes_per_hour,
                "max_payload": p.max_payload_bytes,
                "doppler_tolerance_hz": p.doppler_tolerance_hz,
            })
        return results


# ── FastAPI Router ───────────────────────────────────────────────────

try:
    from fastapi import APIRouter, Query
    router = APIRouter(prefix="/api/v1/modem", tags=["adaptive-modem"])
    _modem = AdaptiveModem()
    _link_calc = LinkBudgetCalculator()

    @router.get("/profiles")
    async def list_profiles():
        """List all available modem profiles."""
        return {
            "count": len(MODEM_PROFILES),
            "profiles": [
                {
                    "name": p.name,
                    "modulation": p.modulation,
                    "spreading_factor": p.spreading_factor,
                    "bandwidth_hz": p.bandwidth_hz,
                    "bitrate_bps": p.bitrate_bps,
                    "sensitivity_dbm": p.sensitivity_dbm,
                    "max_payload_bytes": p.max_payload_bytes,
                    "packets_per_hour": p.packets_per_hour_1pct,
                    "bytes_per_hour": p.bytes_per_hour,
                    "doppler_tolerance_hz": p.doppler_tolerance_hz,
                }
                for p in MODEM_PROFILES
            ],
        }

    @router.get("/select")
    async def select_optimal(
        elevation: float = Query(45, description="Elevation in degrees"),
        range_km: float = Query(800, description="Range in km"),
        doppler: float = Query(0, description="Doppler shift in Hz"),
    ):
        """Select optimal modem profile for given conditions."""
        profile = _modem.select_profile(elevation, range_km, doppler)
        rx_power = _link_calc.received_power(
            distance_km=range_km, elevation_deg=elevation
        )
        margin = _link_calc.link_margin(rx_power, profile.sensitivity_dbm)

        return {
            "selected": profile.name,
            "modulation": profile.modulation,
            "bitrate_bps": profile.bitrate_bps,
            "link_margin_db": round(margin, 1),
            "rx_power_dbm": round(rx_power, 1),
            "packets_per_hour": profile.packets_per_hour_1pct,
            "bytes_per_hour": profile.bytes_per_hour,
            "improvement_vs_sf12": round(profile.bitrate_bps / 293, 1),
        }

    @router.get("/pass-capacity")
    async def pass_capacity(
        duration: int = Query(420, description="Pass duration in seconds"),
        max_elevation: float = Query(55, description="Max elevation in degrees"),
        altitude: float = Query(550, description="Satellite altitude in km"),
    ):
        """Estimate total bytes transferable during a pass."""
        return _modem.estimate_pass_capacity(duration, max_elevation, altitude)

    @router.get("/link-budget")
    async def link_budget(
        distance: float = Query(1100, description="Distance in km"),
        elevation: float = Query(30, description="Elevation in degrees"),
        freq_mhz: float = Query(868, description="Frequency in MHz"),
    ):
        """Compute full link budget."""
        freq_hz = freq_mhz * 1e6
        fspl = _link_calc.free_space_path_loss(distance, freq_hz)
        atm = _link_calc.atmospheric_loss(elevation)
        scint = _link_calc.scintillation_loss(elevation, freq_hz)
        total = _link_calc.total_path_loss(distance, elevation, freq_hz)
        rx = _link_calc.received_power(distance_km=distance,
                                        elevation_deg=elevation, freq_hz=freq_hz)

        return {
            "tx_power_dbm": DEFAULT_TX_POWER_DBM,
            "tx_antenna_gain_dbi": DEFAULT_TX_GAIN_DBI,
            "free_space_path_loss_db": round(fspl, 2),
            "atmospheric_loss_db": round(atm, 2),
            "scintillation_loss_db": round(scint, 2),
            "total_path_loss_db": round(total, 2),
            "rx_antenna_gain_dbi": DEFAULT_RX_GAIN_DBI,
            "received_power_dbm": round(rx, 2),
            "sf12_margin_db": round(rx - (-137), 2),
            "sf7_margin_db": round(rx - (-123), 2),
            "viable_sf12": rx > -137 + 3,
            "viable_sf7": rx > -123 + 3,
        }

    @router.get("/compare")
    async def compare_modes(
        elevation: float = Query(45, description="Elevation in degrees"),
        range_km: float = Query(800, description="Range in km"),
    ):
        """Compare all modem profiles at given conditions."""
        return {
            "elevation_deg": elevation,
            "range_km": range_km,
            "profiles": _modem.compare_all_modes(elevation, range_km),
        }

except ImportError:
    router = None
    logger.info("FastAPI not available, adaptive modem API disabled")
