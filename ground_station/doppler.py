"""
OpenOrbitLink Doppler Compensation Engine

Pre-compensates LoRa uplink frequency for LEO satellite Doppler shift.
At 868 MHz, a satellite at 550 km altitude moving at ~7.5 km/s causes
up to +/-3 kHz Doppler shift. This module computes the required TX
frequency offset at any point during a pass.

Physics:
    Doppler shift = -(v_radial / c) * f_carrier
    where v_radial = range-rate (approaching = negative = positive shift)

Usage:
    compensator = DopplerCompensator(pass_scheduler, carrier_freq_hz=868_000_000)
    offset = compensator.frequency_offset_at(sat_pass, datetime.now(timezone.utc))
    actual_freq = compensator.compensated_frequency(sat_pass, datetime.now(timezone.utc))
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("OpenOrbitLink.Doppler")

# Physical constants
C_LIGHT = 299_792_458.0  # Speed of light (m/s)

# LoRa Doppler tolerance reference
# SF12 BW125: ~1.5 kHz static tolerance, ~200 Hz/s dynamic rate limit
# SF7  BW250: ~10 kHz tolerance, minimal Doppler impact for short packets
LORA_DOPPLER_LIMITS = {
    (7, 125_000): {"static_hz": 5_000, "rate_hz_s": 1_000},
    (7, 250_000): {"static_hz": 10_000, "rate_hz_s": 2_000},
    (8, 125_000): {"static_hz": 4_000, "rate_hz_s": 800},
    (9, 125_000): {"static_hz": 3_000, "rate_hz_s": 600},
    (10, 125_000): {"static_hz": 2_500, "rate_hz_s": 400},
    (11, 125_000): {"static_hz": 2_000, "rate_hz_s": 300},
    (12, 125_000): {"static_hz": 1_500, "rate_hz_s": 200},
}


@dataclass
class DopplerState:
    """Doppler state at a specific instant."""
    timestamp: datetime
    elapsed_s: float
    frequency_offset_hz: float
    range_rate_m_s: float
    range_km: float
    elevation_deg: float
    azimuth_deg: float
    doppler_rate_hz_s: float = 0.0  # Rate of change of Doppler


class DopplerCompensator:
    """
    Pre-compensate LoRa uplink frequency for LEO satellite Doppler.

    Uses Skyfield to compute satellite position/velocity vectors and
    derives the range-rate for Doppler frequency offset calculation.
    """

    def __init__(
        self,
        pass_scheduler,
        carrier_freq_hz: float = 868_000_000,
    ):
        """
        Args:
            pass_scheduler: PassScheduler instance with loaded TLEs
            carrier_freq_hz: Nominal carrier frequency in Hz
        """
        self.scheduler = pass_scheduler
        self.carrier_freq_hz = carrier_freq_hz
        self._cache: dict[str, list[DopplerState]] = {}

    def frequency_offset_at(
        self,
        satellite_name: str,
        t: Optional[datetime] = None,
    ) -> float:
        """
        Compute frequency offset to apply at time t.

        The returned value should be ADDED to the carrier frequency
        to pre-compensate for Doppler shift. The satellite will then
        receive the signal at approximately the nominal frequency.

        Args:
            satellite_name: Name of the target satellite
            t: Time to compute offset for (default: now)

        Returns:
            Frequency offset in Hz (positive = increase TX freq)
        """
        if t is None:
            t = datetime.now(timezone.utc)

        sat = self.scheduler.find_satellite(satellite_name)
        if sat is None:
            return 0.0

        try:
            ts = self.scheduler.ts
            t_sky = ts.from_datetime(t)

            # Compute topocentric position and velocity
            difference = sat - self.scheduler.observer
            topocentric = difference.at(t_sky)

            pos = topocentric.position.km
            vel = topocentric.velocity.km_per_s

            range_km = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)
            if range_km == 0:
                return 0.0

            # Range rate (radial velocity): dot(pos, vel) / |pos|
            # Positive = satellite moving away, negative = approaching
            range_rate_km_s = (
                pos[0] * vel[0] + pos[1] * vel[1] + pos[2] * vel[2]
            ) / range_km
            range_rate_m_s = range_rate_km_s * 1000.0

            # Doppler shift: delta_f = -(v_radial / c) * f_carrier
            # Satellite approaching (negative range_rate) -> positive freq shift
            # Pre-compensation: we apply the OPPOSITE to cancel the shift
            doppler_hz = -(range_rate_m_s / C_LIGHT) * self.carrier_freq_hz

            # Pre-compensation = negate the Doppler (transmit higher when sat approaches)
            return -doppler_hz

        except Exception as e:
            logger.warning(f"Doppler computation failed: {e}")
            return 0.0

    def compensated_frequency(
        self,
        satellite_name: str,
        t: Optional[datetime] = None,
    ) -> float:
        """
        Return the actual TX frequency with Doppler pre-correction.

        Args:
            satellite_name: Target satellite
            t: Time (default: now)

        Returns:
            Compensated frequency in Hz
        """
        offset = self.frequency_offset_at(satellite_name, t)
        return self.carrier_freq_hz + offset

    def offset_profile(
        self,
        satellite_name: str,
        rise_time: datetime,
        duration_s: float,
        step_seconds: float = 1.0,
    ) -> list[DopplerState]:
        """
        Compute full Doppler profile across a pass.

        Args:
            satellite_name: Target satellite
            rise_time: Pass rise time
            duration_s: Pass duration in seconds
            step_seconds: Time step between computations

        Returns:
            List of DopplerState at each time step
        """
        profile: list[DopplerState] = []
        prev_offset = None
        elapsed = 0.0

        while elapsed <= duration_s:
            t = rise_time + timedelta(seconds=elapsed)
            offset = self.frequency_offset_at(satellite_name, t)

            # Compute Doppler rate (Hz/s)
            rate = 0.0
            if prev_offset is not None and step_seconds > 0:
                rate = (offset - prev_offset) / step_seconds

            sat = self.scheduler.find_satellite(satellite_name)
            el_deg = 0.0
            az_deg = 0.0
            range_km = 0.0

            if sat is not None:
                try:
                    ts = self.scheduler.ts
                    t_sky = ts.from_datetime(t)
                    difference = sat - self.scheduler.observer
                    topocentric = difference.at(t_sky)
                    alt, az, dist = topocentric.altaz()
                    el_deg = alt.degrees
                    az_deg = az.degrees
                    range_km = dist.km
                except Exception:
                    pass

            profile.append(DopplerState(
                timestamp=t,
                elapsed_s=round(elapsed, 1),
                frequency_offset_hz=round(offset, 1),
                range_rate_m_s=round(-offset * C_LIGHT / self.carrier_freq_hz, 1),
                range_km=round(range_km, 1),
                elevation_deg=round(el_deg, 1),
                azimuth_deg=round(az_deg, 1),
                doppler_rate_hz_s=round(rate, 1),
            ))

            prev_offset = offset
            elapsed += step_seconds

        return profile

    def make_offset_function(
        self,
        satellite_name: str,
        rise_time: datetime,
        duration_s: float,
    ):
        """
        Create a callable offset function for use during pass transmission.

        Returns a function: elapsed_seconds -> frequency_offset_hz
        that can be passed to PassTransmitter.transmit_during_pass().
        """
        # Pre-compute profile at 1-second resolution
        profile = self.offset_profile(
            satellite_name, rise_time, duration_s, step_seconds=1.0
        )

        offsets = {int(p.elapsed_s): p.frequency_offset_hz for p in profile}

        def offset_fn(elapsed_s: float) -> float:
            idx = int(elapsed_s)
            if idx in offsets:
                return offsets[idx]
            # Interpolate between nearest points
            lower = max(k for k in offsets if k <= idx) if offsets else 0
            upper = min(k for k in offsets if k >= idx) if offsets else 0
            if lower == upper or lower not in offsets or upper not in offsets:
                return offsets.get(lower, 0.0)
            frac = (elapsed_s - lower) / (upper - lower)
            return offsets[lower] + frac * (offsets[upper] - offsets[lower])

        return offset_fn

    @staticmethod
    def is_doppler_safe(
        max_offset_hz: float,
        max_rate_hz_s: float,
        sf: int = 12,
        bw_hz: int = 125_000,
    ) -> bool:
        """
        Check if Doppler conditions are within LoRa tolerance.

        Args:
            max_offset_hz: Peak Doppler offset during pass
            max_rate_hz_s: Maximum Doppler rate during pass
            sf: LoRa spreading factor
            bw_hz: LoRa bandwidth

        Returns:
            True if conditions are within tolerance
        """
        limits = LORA_DOPPLER_LIMITS.get((sf, bw_hz))
        if limits is None:
            # Unknown config -- assume safe with pre-compensation
            return True

        return (
            abs(max_offset_hz) <= limits["static_hz"]
            and abs(max_rate_hz_s) <= limits["rate_hz_s"]
        )

    def recommend_lora_params(
        self,
        satellite_name: str,
        rise_time: datetime,
        duration_s: float,
    ) -> dict:
        """
        Recommend LoRa parameters based on Doppler conditions.

        Analyzes the pass Doppler profile and suggests SF/BW settings
        that will work reliably with pre-compensation.
        """
        profile = self.offset_profile(satellite_name, rise_time, duration_s)

        if not profile:
            return {"sf": 12, "bw_hz": 125_000, "reason": "no_profile_data"}

        max_offset = max(abs(p.frequency_offset_hz) for p in profile)
        max_rate = max(abs(p.doppler_rate_hz_s) for p in profile)

        # Try SF/BW combinations from most efficient to most robust
        candidates = [
            (12, 125_000, "max_range"),
            (11, 125_000, "high_range"),
            (10, 125_000, "balanced"),
            (9, 125_000, "moderate"),
            (8, 125_000, "fast"),
            (7, 125_000, "fastest"),
            (7, 250_000, "widest_tolerance"),
        ]

        for sf, bw, label in candidates:
            if self.is_doppler_safe(max_offset, max_rate, sf, bw):
                return {
                    "sf": sf,
                    "bw_hz": bw,
                    "reason": label,
                    "max_doppler_hz": round(max_offset, 0),
                    "max_doppler_rate_hz_s": round(max_rate, 1),
                    "pre_compensation": max_offset > 500,
                }

        # Fallback: widest bandwidth with pre-compensation
        return {
            "sf": 7,
            "bw_hz": 250_000,
            "reason": "extreme_doppler_fallback",
            "max_doppler_hz": round(max_offset, 0),
            "max_doppler_rate_hz_s": round(max_rate, 1),
            "pre_compensation": True,
        }
