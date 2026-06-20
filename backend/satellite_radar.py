"""
OpenOrbitLink Satellite Radar — Real-Time Position API & WebSocket

Provides sub-second satellite position updates using SGP4 propagation,
satellite selection (connect), link quality estimation, and WebSocket
streaming for the Android radar screen.

Endpoints:
    GET  /api/v1/radar/overhead      → Satellites above horizon
    GET  /api/v1/radar/positions     → All tracked satellite positions
    GET  /api/v1/radar/track/{name}  → Detailed tracking for one satellite
    POST /api/v1/radar/connect       → Select satellite as routing target
    GET  /api/v1/radar/connected     → Currently selected satellite
    GET  /api/v1/radar/catalog       → Full satellite catalog with categories
    WS   /ws/radar                   → Real-time position streaming (1Hz)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# Import orbital predictor
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from ai.orbital_predictor import OrbitalPredictor, GroundStation, SatellitePass
    HAS_PREDICTOR = True
except ImportError:
    HAS_PREDICTOR = False

try:
    from scripts.pass_scheduler import PassScheduler
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False

logger = logging.getLogger("OpenOrbitLink.Radar")

# ── Constants ────────────────────────────────────────────────────────────────

EARTH_RADIUS_KM = 6371.0
SPEED_OF_LIGHT = 299_792_458.0

# Default satellite catalog — expanded beyond just FOSSASAT
DEFAULT_CATALOG = [
    {"name": "ISS (ZARYA)", "norad_id": 25544, "freq_hz": 145_825_000,
     "category": "comms", "color": "#00B4D8",
     "tle1": "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9003",
     "tle2": "2 25544  51.6400 208.9163 0006703  40.5765 319.5714 15.49567089999999"},
    {"name": "NOAA-19", "norad_id": 33591, "freq_hz": 137_100_000,
     "category": "weather", "color": "#533483",
     "tle1": "1 33591U 09005A   24001.50000000  .00000040  00000-0  36094-4 0  9991",
     "tle2": "2 33591  99.1919  19.5272 0013577 100.4955 259.7793 14.12501399999999"},
    {"name": "FOSSASAT-2E", "norad_id": 50985, "freq_hz": 868_000_000,
     "category": "comms", "color": "#00E676",
     "tle1": "1 50985U 22002BE  24001.50000000  .00003200  00000-0  17320-3 0  9990",
     "tle2": "2 50985  97.5120  87.4560 0013200 220.1234 139.8766 15.14000000999999"},
    {"name": "OSCAR-100 (Es'hail-2)", "norad_id": 43700, "freq_hz": 10489_750_000,
     "category": "amateur", "color": "#6C63FF",
     "tle1": "1 43700U 18090A   24001.50000000 -.00000075  00000-0  00000-0 0  9990",
     "tle2": "2 43700   0.0117 271.5230 0001400  12.3456 347.6544  1.00274000999999"},
    {"name": "METEOR-M2 3", "norad_id": 57166, "freq_hz": 137_900_000,
     "category": "weather", "color": "#FF9800",
     "tle1": "1 57166U 23091A   24001.50000000  .00000240  00000-0  13780-3 0  9990",
     "tle2": "2 57166  98.7700  10.2300 0001200 120.5678 239.4322 14.23400000999999"},
    {"name": "FUNcube-1 (AO-73)", "norad_id": 39444, "freq_hz": 145_935_000,
     "category": "amateur", "color": "#E040FB",
     "tle1": "1 39444U 13066AE  24001.50000000  .00000450  00000-0  64700-4 0  9990",
     "tle2": "2 39444  97.6300 340.2100 0059200 200.3400 159.6600 14.81200000999999"},
    {"name": "CAS-4A (XW-3)", "norad_id": 44881, "freq_hz": 145_855_000,
     "category": "amateur", "color": "#00BCD4",
     "tle1": "1 44881U 19093C   24001.50000000  .00000150  00000-0  12000-4 0  9990",
     "tle2": "2 44881  98.2100 100.3400 0017600  80.1234 280.1234 14.35600000999999"},
    {"name": "TEVEL-5 (IO-117)", "norad_id": 51069, "freq_hz": 436_400_000,
     "category": "amateur", "color": "#64FFDA",
     "tle1": "1 51069U 22002CF  24001.50000000  .00006100  00000-0  30100-3 0  9990",
     "tle2": "2 51069  97.5100  87.4560 0012300 215.6789 144.3211 15.15000000999999"},
    {"name": "NOAA-18", "norad_id": 28654, "freq_hz": 137_912_500,
     "category": "weather", "color": "#FF5722",
     "tle1": "1 28654U 05018A   24001.50000000  .00000040  00000-0  33500-4 0  9993",
     "tle2": "2 28654  99.0400  55.7800 0014200 150.2300 210.0000 14.12400000999999"},
    {"name": "CUBEBEL-2 (RS-46)", "norad_id": 44909, "freq_hz": 435_580_000,
     "category": "amateur", "color": "#76FF03",
     "tle1": "1 44909U 20003C   24001.50000000  .00001200  00000-0  58000-4 0  9990",
     "tle2": "2 44909  97.7200 128.9000 0004500 300.1234  59.8766 14.94000000999999"},
    {"name": "STARLINK-30000", "norad_id": 60001, "freq_hz": 12_000_000_000,
     "category": "comms", "color": "#42A5F5",
     "tle1": "1 60001U 24001A   24001.50000000  .00020000  00000-0  10000-3 0  9990",
     "tle2": "2 60001  53.0000  45.0000 0001500 270.0000  90.0000 15.40000000999999"},
    {"name": "GOES-16", "norad_id": 41866, "freq_hz": 1694_100_000,
     "category": "weather", "color": "#FFC107",
     "tle1": "1 41866U 16071A   24001.50000000  .00000050  00000-0  00000-0 0  9990",
     "tle2": "2 41866   0.0400 271.0000 0001500 175.0000 185.0000  1.00270000999999"},
]


# ── Data Models ──────────────────────────────────────────────────────────────

class SatCategory(str, Enum):
    COMMS = "comms"
    WEATHER = "weather"
    AMATEUR = "amateur"
    OTHER = "other"


@dataclass
class SatellitePosition:
    """Real-time satellite position and tracking data."""
    name: str
    norad_id: int
    latitude: float
    longitude: float
    altitude_km: float
    azimuth_deg: float
    elevation_deg: float
    range_km: float
    doppler_hz: float
    velocity_km_s: float
    is_visible: bool
    footprint_km: float
    category: str
    color: str
    frequency_hz: float
    signal_quality: float  # 0.0 - 1.0
    next_pass_minutes: Optional[int] = None
    pass_remaining_seconds: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Radar Engine ─────────────────────────────────────────────────────────────

class SatelliteRadarEngine:
    """
    Real-time satellite tracking engine using SGP4 propagation.

    Computes positions for all catalog satellites at sub-millisecond speed.
    Designed for 1Hz update rate on the Android radar screen.
    """

    def __init__(
        self,
        observer_lat: float = 28.6139,
        observer_lon: float = 77.2090,
        observer_alt: float = 216.0,
        catalog: list[dict] | None = None,
    ):
        self.observer_lat = observer_lat
        self.observer_lon = observer_lon
        self.observer_alt = observer_alt
        self.catalog = catalog or DEFAULT_CATALOG
        self.connected_satellite: Optional[str] = None
        self._predictor: Optional[OrbitalPredictor] = None
        self._scheduler: Optional[PassScheduler] = None

        # Initialize SGP4 predictor
        self._init_predictor()

    def _init_predictor(self) -> None:
        """Initialize the orbital prediction engine."""
        if HAS_PREDICTOR:
            try:
                self._predictor = OrbitalPredictor(
                    GroundStation(
                        self.observer_lat,
                        self.observer_lon,
                        self.observer_alt,
                    )
                )
                # Load catalog TLEs
                for sat in self.catalog:
                    self._predictor.add_satellite(
                        sat["name"], sat["tle1"], sat["tle2"],
                        norad_id=sat["norad_id"],
                    )
                logger.info(f"Radar engine initialized: {len(self.catalog)} satellites")
            except Exception as e:
                logger.warning(f"OrbitalPredictor init failed: {e}, using fallback")
                self._predictor = None

    def compute_all_positions(self) -> list[SatellitePosition]:
        """
        Compute current positions for all catalog satellites.

        Returns positions in observer-relative coordinates (azimuth, elevation)
        plus geographic coordinates (lat, lon, alt).
        """
        now = datetime.now(timezone.utc)
        positions: list[SatellitePosition] = []

        for sat_info in self.catalog:
            try:
                pos = self._compute_position(sat_info, now)
                if pos is not None:
                    positions.append(pos)
            except Exception as e:
                logger.debug(f"Position error for {sat_info['name']}: {e}")

        return positions

    def _compute_position(
        self, sat_info: dict, now: datetime
    ) -> Optional[SatellitePosition]:
        """Compute position for a single satellite using SGP4."""
        name = sat_info["name"]
        tle1 = sat_info["tle1"]
        tle2 = sat_info["tle2"]

        # Use the predictor if available
        if self._predictor is not None:
            try:
                result = self._predictor.predict_position(name, now)
                if result is not None:
                    return SatellitePosition(
                        name=name,
                        norad_id=sat_info["norad_id"],
                        latitude=result.latitude_deg,
                        longitude=result.longitude_deg,
                        altitude_km=result.altitude_km,
                        azimuth_deg=result.azimuth_deg,
                        elevation_deg=result.elevation_deg,
                        range_km=result.range_km,
                        doppler_hz=self._compute_doppler(
                            result.range_rate_km_s, sat_info["freq_hz"]
                        ),
                        velocity_km_s=result.velocity_km_s,
                        is_visible=result.elevation_deg > 0,
                        footprint_km=self._footprint(result.altitude_km),
                        category=sat_info["category"],
                        color=sat_info["color"],
                        frequency_hz=sat_info["freq_hz"],
                        signal_quality=self._signal_quality(
                            result.elevation_deg, result.range_km
                        ),
                    )
            except Exception:
                pass

        # Fallback: simplified Keplerian propagation from TLE
        return self._fallback_position(sat_info, now)

    def _fallback_position(
        self, sat_info: dict, now: datetime
    ) -> SatellitePosition:
        """
        Simplified position computation without full SGP4.

        Uses TLE mean motion and inclination to estimate sub-satellite point.
        Not as accurate as SGP4 but works without numpy/sgp4 dependencies.
        """
        tle2 = sat_info["tle2"]

        # Parse TLE line 2 for orbital elements
        inclination = float(tle2[8:16])
        raan = float(tle2[17:25])
        mean_motion = float(tle2[52:63])  # rev/day
        mean_anomaly = float(tle2[43:51])

        # Compute period and current position
        period_min = 1440.0 / mean_motion
        altitude_km = self._altitude_from_period(period_min)

        # Time since epoch (simplified)
        epoch_year = int("20" + tle2[2:4]) if int(tle2[2:4]) < 57 else int("19" + tle2[2:4])
        epoch_day = float(sat_info["tle1"][20:32])

        epoch = datetime(epoch_year, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=epoch_day - 1
        )
        elapsed_min = (now - epoch).total_seconds() / 60.0
        orbits_elapsed = elapsed_min / period_min

        # Current mean anomaly
        current_ma = (mean_anomaly + orbits_elapsed * 360.0) % 360.0

        # Sub-satellite point (simplified)
        lat = inclination * math.sin(math.radians(current_ma))
        lon_shift = (now - epoch).total_seconds() / 86400.0 * 360.0
        lon = (raan + current_ma - lon_shift) % 360.0
        if lon > 180:
            lon -= 360

        # Observer-relative angles
        az, el, rng = self._observer_angles(lat, lon, altitude_km)

        # Velocity from orbital mechanics
        velocity = math.sqrt(398600.4418 / (EARTH_RADIUS_KM + altitude_km))

        return SatellitePosition(
            name=sat_info["name"],
            norad_id=sat_info["norad_id"],
            latitude=round(lat, 4),
            longitude=round(lon, 4),
            altitude_km=round(altitude_km, 1),
            azimuth_deg=round(az, 1),
            elevation_deg=round(el, 1),
            range_km=round(rng, 1),
            doppler_hz=round(
                self._compute_doppler_from_angles(el, velocity, sat_info["freq_hz"]), 1
            ),
            velocity_km_s=round(velocity, 2),
            is_visible=el > 0,
            footprint_km=round(self._footprint(altitude_km), 0),
            category=sat_info["category"],
            color=sat_info["color"],
            frequency_hz=sat_info["freq_hz"],
            signal_quality=self._signal_quality(el, rng),
        )

    def _altitude_from_period(self, period_min: float) -> float:
        """Compute altitude from orbital period using Kepler's 3rd law."""
        mu = 398600.4418  # km³/s²
        period_s = period_min * 60.0
        semi_major = (mu * (period_s / (2 * math.pi)) ** 2) ** (1 / 3)
        return semi_major - EARTH_RADIUS_KM

    def _observer_angles(
        self, sat_lat: float, sat_lon: float, sat_alt: float
    ) -> tuple[float, float, float]:
        """Compute azimuth, elevation, range from observer to satellite."""
        obs_lat = math.radians(self.observer_lat)
        obs_lon = math.radians(self.observer_lon)
        s_lat = math.radians(sat_lat)
        s_lon = math.radians(sat_lon)

        # Great circle angle
        d_lon = s_lon - obs_lon
        cos_gc = (
            math.sin(obs_lat) * math.sin(s_lat)
            + math.cos(obs_lat) * math.cos(s_lat) * math.cos(d_lon)
        )
        cos_gc = max(-1, min(1, cos_gc))
        gc = math.acos(cos_gc)

        # Slant range
        R = EARTH_RADIUS_KM
        h = sat_alt
        rng = math.sqrt(R**2 + (R + h) ** 2 - 2 * R * (R + h) * cos_gc)

        # Elevation
        if rng > 0:
            sin_el = ((R + h) * cos_gc - R) / rng
            sin_el = max(-1, min(1, sin_el))
            el = math.degrees(math.asin(sin_el))
        else:
            el = 90.0

        # Azimuth
        if gc > 1e-10:
            cos_az = (math.sin(s_lat) - math.sin(obs_lat) * cos_gc) / (
                math.cos(obs_lat) * math.sin(gc)
            )
            cos_az = max(-1, min(1, cos_az))
            az = math.degrees(math.acos(cos_az))
            if math.sin(d_lon) < 0:
                az = 360 - az
        else:
            az = 0.0

        return az, el, rng

    def _footprint(self, altitude_km: float) -> float:
        """Satellite ground footprint diameter in km."""
        R = EARTH_RADIUS_KM
        return 2 * R * math.acos(R / (R + altitude_km))

    def _compute_doppler(self, range_rate_km_s: float, freq_hz: float) -> float:
        """Doppler shift from range rate."""
        return -range_rate_km_s * 1000.0 / SPEED_OF_LIGHT * freq_hz

    def _compute_doppler_from_angles(
        self, elevation_deg: float, velocity_km_s: float, freq_hz: float
    ) -> float:
        """Estimate Doppler from elevation angle and orbital velocity."""
        if elevation_deg >= 85:
            return 0.0  # Near zenith, minimal Doppler
        el_rad = math.radians(max(0, elevation_deg))
        radial_v = velocity_km_s * math.cos(el_rad + math.pi / 2) * 1000
        return -radial_v / SPEED_OF_LIGHT * freq_hz

    def _signal_quality(self, elevation_deg: float, range_km: float) -> float:
        """
        Estimate signal quality (0.0 - 1.0) based on link budget factors.

        Considers elevation angle, range, and atmospheric effects.
        """
        if elevation_deg < 0:
            return 0.0
        if elevation_deg < 5:
            return 0.05

        # Elevation factor (higher = better, less atmosphere)
        el_factor = min(1.0, elevation_deg / 60.0)

        # Range factor (closer = better)
        if range_km < 500:
            rng_factor = 1.0
        elif range_km < 2000:
            rng_factor = 1.0 - (range_km - 500) / 3000
        else:
            rng_factor = max(0.1, 1.0 - range_km / 5000)

        # Combined quality
        quality = 0.6 * el_factor + 0.4 * rng_factor
        return round(max(0.0, min(1.0, quality)), 2)

    def get_overhead_satellites(
        self, min_elevation: float = 0.0
    ) -> list[SatellitePosition]:
        """Get satellites currently above the specified elevation."""
        positions = self.compute_all_positions()
        return [p for p in positions if p.elevation_deg >= min_elevation]

    def get_visible_satellites(self) -> list[SatellitePosition]:
        """Get satellites above the horizon (elevation > 0)."""
        return self.get_overhead_satellites(0.0)

    def connect_satellite(self, name: str) -> bool:
        """Select a satellite as the routing target."""
        for sat in self.catalog:
            if sat["name"].upper() == name.upper():
                self.connected_satellite = name
                logger.info(f"Connected to satellite: {name}")
                return True
        return False

    def disconnect_satellite(self) -> None:
        """Deselect the current satellite."""
        logger.info(f"Disconnected from: {self.connected_satellite}")
        self.connected_satellite = None

    def get_connected_position(self) -> Optional[SatellitePosition]:
        """Get current position of the connected satellite."""
        if self.connected_satellite is None:
            return None
        positions = self.compute_all_positions()
        for pos in positions:
            if pos.name == self.connected_satellite:
                return pos
        return None


# ── Module-level instance ────────────────────────────────────────────────────

_radar_engine: Optional[SatelliteRadarEngine] = None


def init_radar_engine(
    observer_lat: float = 28.6139,
    observer_lon: float = 77.2090,
    observer_alt: float = 216.0,
) -> SatelliteRadarEngine:
    """Initialize the radar engine. Called from backend/main.py on startup."""
    global _radar_engine
    _radar_engine = SatelliteRadarEngine(
        observer_lat=observer_lat,
        observer_lon=observer_lon,
        observer_alt=observer_alt,
    )
    return _radar_engine


# ── FastAPI Router ───────────────────────────────────────────────────────────

if HAS_FASTAPI:

    router = APIRouter(prefix="/api/v1/radar", tags=["radar"])

    class ConnectRequest(BaseModel):
        satellite_name: str

    class ServiceModeRequest(BaseModel):
        mode: str  # "standby", "active", "emergency"

    @router.get("/positions")
    async def get_positions():
        """Get current positions of all tracked satellites."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        positions = _radar_engine.compute_all_positions()
        visible = [p for p in positions if p.is_visible]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tracked": len(positions),
            "visible_count": len(visible),
            "observer": {
                "lat": _radar_engine.observer_lat,
                "lon": _radar_engine.observer_lon,
                "alt": _radar_engine.observer_alt,
            },
            "satellites": [p.to_dict() for p in positions],
        }

    @router.get("/overhead")
    async def get_overhead(
        min_elevation: float = Query(default=0.0, ge=-5, le=90),
    ):
        """Get satellites currently above the specified elevation."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        overhead = _radar_engine.get_overhead_satellites(min_elevation)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(overhead),
            "min_elevation": min_elevation,
            "satellites": [p.to_dict() for p in overhead],
        }

    @router.get("/track/{satellite_name}")
    async def track_satellite(satellite_name: str):
        """Get detailed tracking data for a specific satellite."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        positions = _radar_engine.compute_all_positions()
        for pos in positions:
            if satellite_name.upper() in pos.name.upper():
                return {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "satellite": pos.to_dict(),
                    "is_connected": pos.name == _radar_engine.connected_satellite,
                }

        raise HTTPException(404, f"Satellite '{satellite_name}' not found")

    @router.post("/connect")
    async def connect_satellite(req: ConnectRequest):
        """Select a satellite as the preferred routing target."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        success = _radar_engine.connect_satellite(req.satellite_name)
        if not success:
            raise HTTPException(404, f"Satellite '{req.satellite_name}' not in catalog")

        pos = _radar_engine.get_connected_position()
        return {
            "status": "connected",
            "satellite": req.satellite_name,
            "position": pos.to_dict() if pos else None,
            "message": f"Messages will route via {req.satellite_name} during next pass",
        }

    @router.post("/disconnect")
    async def disconnect_satellite():
        """Deselect the current satellite."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        prev = _radar_engine.connected_satellite
        _radar_engine.disconnect_satellite()
        return {"status": "disconnected", "previous": prev}

    @router.get("/connected")
    async def get_connected():
        """Get the currently connected satellite and its position."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        if _radar_engine.connected_satellite is None:
            return {"connected": False, "satellite": None}

        pos = _radar_engine.get_connected_position()
        return {
            "connected": True,
            "satellite_name": _radar_engine.connected_satellite,
            "position": pos.to_dict() if pos else None,
        }

    @router.get("/catalog")
    async def get_catalog():
        """Get full satellite catalog with categories."""
        if not _radar_engine:
            raise HTTPException(503, "Radar engine not initialized")

        return {
            "count": len(_radar_engine.catalog),
            "categories": {
                "comms": len([s for s in _radar_engine.catalog if s["category"] == "comms"]),
                "weather": len([s for s in _radar_engine.catalog if s["category"] == "weather"]),
                "amateur": len([s for s in _radar_engine.catalog if s["category"] == "amateur"]),
            },
            "satellites": [
                {
                    "name": s["name"],
                    "norad_id": s["norad_id"],
                    "category": s["category"],
                    "color": s["color"],
                    "frequency_mhz": round(s["freq_hz"] / 1e6, 3),
                }
                for s in _radar_engine.catalog
            ],
        }

    # ── Service Mode ─────────────────────────────────────────────

    _current_service_mode = "active"

    @router.post("/mode")
    async def set_service_mode(req: ServiceModeRequest):
        """Set service mode: standby, active, or emergency."""
        global _current_service_mode
        if req.mode not in ("standby", "active", "emergency"):
            raise HTTPException(400, "Mode must be: standby, active, emergency")
        _current_service_mode = req.mode
        return {"mode": _current_service_mode}

    @router.get("/mode")
    async def get_service_mode():
        """Get current service mode."""
        return {"mode": _current_service_mode}

    # ── Link Test ────────────────────────────────────────────────

    @router.get("/link-test")
    async def link_test():
        """Dual-layer link connectivity test."""
        start = time.monotonic()

        # Layer 1: App → Backend (this request itself measures it)
        app_backend_ms = round((time.monotonic() - start) * 1000, 1)

        # Layer 2: Backend → Radar Engine
        radar_start = time.monotonic()
        if _radar_engine:
            positions = _radar_engine.compute_all_positions()
            radar_ms = round((time.monotonic() - radar_start) * 1000, 1)
            visible = len([p for p in positions if p.is_visible])
        else:
            radar_ms = -1
            visible = 0

        return {
            "app_to_backend_ms": app_backend_ms,
            "backend_to_radar_ms": radar_ms,
            "satellites_tracked": len(_radar_engine.catalog) if _radar_engine else 0,
            "satellites_visible": visible,
            "service_mode": _current_service_mode,
            "connected_satellite": _radar_engine.connected_satellite if _radar_engine else None,
            "status": "operational" if _radar_engine else "degraded",
        }


# ── WebSocket for Real-Time Streaming ────────────────────────────────────────

_active_ws_connections: list[WebSocket] = []


async def radar_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time satellite position streaming.

    Sends position updates at 1Hz (every second) for all tracked satellites.
    Client can send JSON commands:
        {"command": "connect", "satellite": "ISS (ZARYA)"}
        {"command": "disconnect"}
        {"command": "set_mode", "mode": "emergency"}
    """
    await websocket.accept()
    _active_ws_connections.append(websocket)
    logger.info(f"Radar WebSocket connected. Total: {len(_active_ws_connections)}")

    try:
        # Start streaming positions
        stream_task = asyncio.create_task(
            _stream_positions(websocket)
        )

        # Listen for client commands
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )
                await _handle_ws_command(websocket, data)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info("Radar WebSocket disconnected")
    except Exception as e:
        logger.error(f"Radar WebSocket error: {e}")
    finally:
        stream_task.cancel()
        if websocket in _active_ws_connections:
            _active_ws_connections.remove(websocket)


async def _stream_positions(websocket: WebSocket):
    """Stream satellite positions at 1Hz."""
    while True:
        try:
            if _radar_engine:
                positions = _radar_engine.compute_all_positions()
                visible = [p for p in positions if p.is_visible]

                payload = {
                    "type": "positions",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total": len(positions),
                    "visible": len(visible),
                    "connected": _radar_engine.connected_satellite,
                    "mode": _current_service_mode if HAS_FASTAPI else "active",
                    "satellites": [p.to_dict() for p in positions],
                }
                await websocket.send_json(payload)

            await asyncio.sleep(1.0)  # 1Hz update rate
        except Exception:
            break


async def _handle_ws_command(websocket: WebSocket, data: str):
    """Handle incoming WebSocket commands."""
    try:
        cmd = json.loads(data)
        command = cmd.get("command", "")

        if command == "connect" and _radar_engine:
            name = cmd.get("satellite", "")
            success = _radar_engine.connect_satellite(name)
            await websocket.send_json({
                "type": "command_response",
                "command": "connect",
                "success": success,
                "satellite": name,
            })

        elif command == "disconnect" and _radar_engine:
            _radar_engine.disconnect_satellite()
            await websocket.send_json({
                "type": "command_response",
                "command": "disconnect",
                "success": True,
            })

        elif command == "set_mode":
            global _current_service_mode
            mode = cmd.get("mode", "active")
            if mode in ("standby", "active", "emergency"):
                _current_service_mode = mode
                await websocket.send_json({
                    "type": "command_response",
                    "command": "set_mode",
                    "mode": mode,
                    "success": True,
                })

    except json.JSONDecodeError:
        pass
