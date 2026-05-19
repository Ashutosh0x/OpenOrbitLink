"""
OpenOrbitLink Satellite Pass Scheduler

SGP4-based satellite pass prediction using Skyfield. Computes rise/set times,
max elevation, Doppler profiles, and transmit windows for FOSSASAT-2E, ISS,
and other target satellites.

Usage:
    python scripts/pass_scheduler.py --tle data/openorbitlink_satellites.tle
    python scripts/pass_scheduler.py --satellite ISS --hours 48
    python scripts/pass_scheduler.py --json --output data/passes.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    from skyfield.api import EarthSatellite, Topos, load, wgs84
    from skyfield.timelib import Time
    HAS_SKYFIELD = True
except ImportError:
    HAS_SKYFIELD = False

# Speed of light (m/s)
C_LIGHT = 299_792_458.0

# Default observer: New Delhi, India
DEFAULT_LAT = 28.6139
DEFAULT_LON = 77.2090
DEFAULT_ALT = 216.0  # meters

# Satellites of interest
TARGET_SATELLITES = {
    "ISS (ZARYA)": {"norad_id": 25544, "frequency_hz": 145_825_000},
    "FOSSASAT-2E": {"norad_id": 0, "frequency_hz": 868_000_000},
    "FOSSASAT-2E4": {"norad_id": 0, "frequency_hz": 868_000_000},
}


@dataclass
class DopplerPoint:
    """Doppler shift at a specific time during a pass."""
    elapsed_s: float
    timestamp: str
    frequency_offset_hz: float
    range_rate_m_s: float
    range_km: float
    elevation_deg: float
    azimuth_deg: float


@dataclass
class SatellitePass:
    """A single satellite pass over the observer."""
    satellite_name: str
    norad_id: int
    rise_time: str
    rise_azimuth_deg: float
    culmination_time: str
    max_elevation_deg: float
    set_time: str
    set_azimuth_deg: float
    duration_s: float
    frequency_hz: float = 868_000_000
    doppler_profile: list[DopplerPoint] = field(default_factory=list)

    @property
    def is_high_pass(self) -> bool:
        """Pass with max elevation > 45 degrees -- best for communication."""
        return self.max_elevation_deg > 45.0

    @property
    def usable_window_s(self) -> float:
        """Estimated usable TX window (elevation > 10 degrees)."""
        return self.duration_s

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_high_pass"] = self.is_high_pass
        d["usable_window_s"] = self.usable_window_s
        return d


class PassScheduler:
    """
    SGP4-based satellite pass predictor.

    Uses Skyfield to compute satellite passes over an observer location,
    including rise/set times, max elevation, and Doppler shift profiles.
    """

    def __init__(
        self,
        tle_path: str = "data/openorbitlink_satellites.tle",
        observer_lat: float = DEFAULT_LAT,
        observer_lon: float = DEFAULT_LON,
        observer_alt: float = DEFAULT_ALT,
    ):
        if not HAS_SKYFIELD:
            raise RuntimeError(
                "Skyfield required for pass prediction: pip install skyfield"
            )

        self.tle_path = tle_path
        self.observer_lat = observer_lat
        self.observer_lon = observer_lon
        self.observer_alt = observer_alt

        self.ts = load.timescale()
        self.observer = wgs84.latlon(observer_lat, observer_lon, observer_alt)
        self.satellites: dict[str, EarthSatellite] = {}

        if os.path.exists(tle_path):
            self._load_tles(tle_path)

    def _load_tles(self, tle_path: str) -> None:
        """Load satellites from a TLE file."""
        sats = load.tle_file(tle_path)
        for sat in sats:
            self.satellites[sat.name.strip()] = sat
        if self.satellites:
            print(f"Loaded {len(self.satellites)} satellites from {tle_path}")

    def add_tle(self, name: str, line1: str, line2: str) -> None:
        """Add a satellite from raw TLE lines."""
        sat = EarthSatellite(line1, line2, name, self.ts)
        self.satellites[name.strip()] = sat

    def list_satellites(self) -> list[str]:
        """Return names of all loaded satellites."""
        return sorted(self.satellites.keys())

    def find_satellite(self, name_fragment: str) -> Optional[EarthSatellite]:
        """Find a satellite by partial name match (case-insensitive)."""
        fragment = name_fragment.upper()
        for name, sat in self.satellites.items():
            if fragment in name.upper():
                return sat
        return None

    def next_passes(
        self,
        satellite_name: str,
        hours_ahead: float = 24.0,
        min_elevation: float = 10.0,
    ) -> list[SatellitePass]:
        """
        Compute next satellite passes over the observer.

        Args:
            satellite_name: Full or partial satellite name
            hours_ahead: How many hours ahead to search
            min_elevation: Minimum peak elevation in degrees

        Returns:
            List of SatellitePass objects sorted by rise time
        """
        sat = self.find_satellite(satellite_name)
        if sat is None:
            return []

        t0 = self.ts.now()
        t1 = self.ts.utc(
            t0.utc_datetime() + timedelta(hours=hours_ahead)
        )

        try:
            t_events, events = sat.find_events(
                self.observer, t0, t1, altitude_degrees=min_elevation
            )
        except Exception:
            return []

        passes: list[SatellitePass] = []
        i = 0
        while i < len(events):
            # Collect rise (0), culminate (1), set (2) triplet
            if events[i] == 0:  # Rise
                rise_t = t_events[i]
                rise_az = self._azimuth_at(sat, rise_t)
                culm_t = None
                culm_el = 0.0
                set_t = None
                set_az = 0.0

                i += 1
                while i < len(events) and events[i] != 0:
                    if events[i] == 1:  # Culmination
                        culm_t = t_events[i]
                        culm_el = self._elevation_at(sat, culm_t)
                    elif events[i] == 2:  # Set
                        set_t = t_events[i]
                        set_az = self._azimuth_at(sat, set_t)
                    i += 1

                if set_t is not None and culm_t is not None:
                    duration = (set_t.utc_datetime() - rise_t.utc_datetime()).total_seconds()

                    # Get frequency for this satellite
                    freq_hz = 868_000_000
                    for tgt_name, info in TARGET_SATELLITES.items():
                        if tgt_name.upper() in sat.name.upper():
                            freq_hz = info["frequency_hz"]
                            break

                    sat_pass = SatellitePass(
                        satellite_name=sat.name.strip(),
                        norad_id=sat.model.satnum,
                        rise_time=rise_t.utc_iso(),
                        rise_azimuth_deg=round(rise_az, 1),
                        culmination_time=culm_t.utc_iso(),
                        max_elevation_deg=round(culm_el, 1),
                        set_time=set_t.utc_iso(),
                        set_azimuth_deg=round(set_az, 1),
                        duration_s=round(duration, 1),
                        frequency_hz=freq_hz,
                    )
                    passes.append(sat_pass)
            else:
                i += 1

        return passes

    def next_pass(self, satellite_name: str) -> Optional[SatellitePass]:
        """Get the next single pass for a satellite."""
        passes = self.next_passes(satellite_name, hours_ahead=48.0)
        return passes[0] if passes else None

    def doppler_profile(
        self,
        sat_pass: SatellitePass,
        frequency_hz: Optional[float] = None,
        step_seconds: float = 5.0,
    ) -> list[DopplerPoint]:
        """
        Compute Doppler shift profile for a satellite pass.

        Uses Skyfield position/velocity vectors to compute range-rate,
        then derives frequency offset: delta_f = -v_radial / c * f_carrier

        Args:
            sat_pass: The satellite pass to analyze
            frequency_hz: Carrier frequency (default: pass frequency)
            step_seconds: Time step between Doppler calculations

        Returns:
            List of DopplerPoint with offset at each time step
        """
        sat = self.find_satellite(sat_pass.satellite_name)
        if sat is None:
            return []

        freq = frequency_hz or sat_pass.frequency_hz

        # Parse rise/set times
        rise_dt = datetime.fromisoformat(sat_pass.rise_time.replace("Z", "+00:00"))
        set_dt = datetime.fromisoformat(sat_pass.set_time.replace("Z", "+00:00"))
        duration = (set_dt - rise_dt).total_seconds()

        profile: list[DopplerPoint] = []
        elapsed = 0.0

        while elapsed <= duration:
            t_dt = rise_dt + timedelta(seconds=elapsed)
            t = self.ts.from_datetime(t_dt)

            # Compute topocentric position and velocity
            difference = sat - self.observer
            topocentric = difference.at(t)

            # Position in km
            pos = topocentric.position.km
            range_km = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)

            # Velocity in km/s
            vel = topocentric.velocity.km_per_s

            # Range rate (radial velocity) = dot(pos, vel) / |pos|
            range_rate = (pos[0]*vel[0] + pos[1]*vel[1] + pos[2]*vel[2]) / range_km
            range_rate_m_s = range_rate * 1000.0  # km/s -> m/s

            # Doppler shift: delta_f = -v_radial / c * f_carrier
            doppler_hz = -range_rate_m_s / C_LIGHT * freq

            # Elevation and azimuth
            alt_deg, az_deg, _ = topocentric.altaz()

            profile.append(DopplerPoint(
                elapsed_s=round(elapsed, 1),
                timestamp=t_dt.isoformat(),
                frequency_offset_hz=round(doppler_hz, 1),
                range_rate_m_s=round(range_rate_m_s, 1),
                range_km=round(range_km, 1),
                elevation_deg=round(alt_deg.degrees, 1),
                azimuth_deg=round(az_deg.degrees, 1),
            ))

            elapsed += step_seconds

        return profile

    def should_transmit_now(
        self,
        satellite_name: str,
        min_elevation: float = 10.0,
    ) -> tuple[bool, Optional[SatellitePass]]:
        """
        Check if a satellite is currently overhead and we should transmit.

        Returns:
            Tuple of (should_transmit, current_pass_or_None)
        """
        sat = self.find_satellite(satellite_name)
        if sat is None:
            return False, None

        t = self.ts.now()
        el = self._elevation_at(sat, t)

        if el >= min_elevation:
            # Satellite is overhead -- find the current pass details
            next_p = self.next_pass(satellite_name)
            return True, next_p

        return False, None

    def all_upcoming_passes(
        self,
        hours_ahead: float = 24.0,
        min_elevation: float = 10.0,
    ) -> list[SatellitePass]:
        """Get all passes for all loaded satellites, sorted by rise time."""
        all_passes: list[SatellitePass] = []
        for name in self.satellites:
            passes = self.next_passes(name, hours_ahead, min_elevation)
            all_passes.extend(passes)

        all_passes.sort(key=lambda p: p.rise_time)
        return all_passes

    def time_to_next_pass(self, satellite_name: str) -> Optional[float]:
        """Seconds until the next pass starts. None if no pass found."""
        p = self.next_pass(satellite_name)
        if p is None:
            return None
        rise_dt = datetime.fromisoformat(p.rise_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (rise_dt - now).total_seconds()
        return max(0.0, delta)

    # --- Internal helpers ---

    def _elevation_at(self, sat: 'EarthSatellite', t: 'Time') -> float:
        """Get elevation in degrees at time t."""
        difference = sat - self.observer
        topocentric = difference.at(t)
        alt, _, _ = topocentric.altaz()
        return alt.degrees

    def _azimuth_at(self, sat: 'EarthSatellite', t: 'Time') -> float:
        """Get azimuth in degrees at time t."""
        difference = sat - self.observer
        topocentric = difference.at(t)
        _, az, _ = topocentric.altaz()
        return az.degrees


def format_pass_table(passes: list[SatellitePass]) -> str:
    """Format passes as a human-readable table."""
    if not passes:
        return "  No passes found.\n"

    lines = []
    lines.append(f"  {'Satellite':<24} {'Rise (UTC)':<22} {'Max El':>7} {'Duration':>9} {'Set (UTC)':<22}")
    lines.append("  " + "-" * 88)

    for p in passes:
        rise_short = p.rise_time[:19].replace("T", " ")
        set_short = p.set_time[:19].replace("T", " ")
        quality = "*" if p.is_high_pass else " "
        lines.append(
            f" {quality}{p.satellite_name:<23} {rise_short:<22} {p.max_elevation_deg:>5.1f}d "
            f"{p.duration_s:>7.0f}s {set_short:<22}"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenOrbitLink Satellite Pass Scheduler")
    parser.add_argument("--tle", default="data/openorbitlink_satellites.tle",
                        help="Path to TLE file")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT,
                        help="Observer latitude")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON,
                        help="Observer longitude")
    parser.add_argument("--alt", type=float, default=DEFAULT_ALT,
                        help="Observer altitude (meters)")
    parser.add_argument("--satellite", default=None,
                        help="Filter by satellite name (partial match)")
    parser.add_argument("--hours", type=float, default=24.0,
                        help="Hours ahead to search")
    parser.add_argument("--min-elevation", type=float, default=10.0,
                        help="Minimum peak elevation (degrees)")
    parser.add_argument("--doppler", action="store_true",
                        help="Include Doppler profiles")
    parser.add_argument("--doppler-freq", type=float, default=None,
                        help="Carrier frequency for Doppler (Hz)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--output", default=None,
                        help="Output file path")
    args = parser.parse_args()

    scheduler = PassScheduler(
        tle_path=args.tle,
        observer_lat=args.lat,
        observer_lon=args.lon,
        observer_alt=args.alt,
    )

    if not scheduler.satellites:
        print("No satellites loaded. Run: python scripts/fetch_tle.py --all-openorbitlink --include-fossa")
        sys.exit(1)

    print(f"\nObserver: ({args.lat:.4f}, {args.lon:.4f}) alt {args.alt:.0f}m")
    print(f"Satellites loaded: {len(scheduler.satellites)}")
    print(f"Search window: {args.hours:.0f} hours\n")

    if args.satellite:
        passes = scheduler.next_passes(args.satellite, args.hours, args.min_elevation)
    else:
        passes = scheduler.all_upcoming_passes(args.hours, args.min_elevation)

    if args.doppler:
        for p in passes:
            p.doppler_profile = scheduler.doppler_profile(
                p, frequency_hz=args.doppler_freq
            )

    if args.json:
        output = json.dumps([p.to_dict() for p in passes], indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"Wrote {len(passes)} passes to {args.output}")
        else:
            print(output)
    else:
        print(format_pass_table(passes))
        if passes:
            next_p = passes[0]
            eta = scheduler.time_to_next_pass(next_p.satellite_name)
            if eta is not None and eta > 0:
                mins = int(eta // 60)
                print(f"\n  Next pass: {next_p.satellite_name} in {mins} min")
            elif eta == 0:
                print(f"\n  ** {next_p.satellite_name} is overhead NOW **")

            if args.doppler and next_p.doppler_profile:
                print(f"\n  Doppler profile ({next_p.satellite_name} @ {next_p.frequency_hz/1e6:.3f} MHz):")
                print(f"  {'Time':>8} {'Offset Hz':>12} {'Range km':>10} {'El':>6} {'Az':>6}")
                print("  " + "-" * 48)
                for dp in next_p.doppler_profile[::3]:  # Every 3rd point
                    print(
                        f"  {dp.elapsed_s:>7.0f}s {dp.frequency_offset_hz:>+11.0f} "
                        f"{dp.range_km:>9.0f} {dp.elevation_deg:>5.1f} {dp.azimuth_deg:>5.1f}"
                    )


if __name__ == "__main__":
    main()
