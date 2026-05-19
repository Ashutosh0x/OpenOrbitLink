"""
OpenOrbitLink Satellite Pass API -- FastAPI Endpoints for Pass Prediction

Provides REST endpoints for satellite pass prediction, duty cycle monitoring,
and message status tracking.

Endpoints:
    GET /api/v1/passes          -> Next passes for all satellites
    GET /api/v1/passes/next     -> Next single pass
    GET /api/v1/passes/{satellite} -> Passes for specific satellite
    GET /api/v1/duty_cycle      -> Current duty cycle budget
    GET /api/v1/messages/{id}/status -> Message delivery status
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Query
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# Import pass scheduler
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from scripts.pass_scheduler import PassScheduler
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False

router = APIRouter(prefix="/api/v1", tags=["satellite"])

# Module-level scheduler instance (initialized in main.py startup)
_scheduler: Optional[PassScheduler] = None
_duty_cycle_tracker = None


def init_pass_scheduler(
    tle_path: str = "data/openorbitlink_satellites.tle",
    lat: float = 28.6139,
    lon: float = 77.2090,
    alt: float = 216.0,
) -> Optional[PassScheduler]:
    """Initialize the pass scheduler. Called from backend/main.py on startup."""
    global _scheduler

    if not HAS_SCHEDULER:
        return None

    if not Path(tle_path).exists():
        return None

    _scheduler = PassScheduler(
        tle_path=tle_path,
        observer_lat=lat,
        observer_lon=lon,
        observer_alt=alt,
    )
    return _scheduler


if HAS_FASTAPI:

    @router.get("/passes")
    async def get_passes(
        hours: float = Query(default=24.0, ge=1, le=168),
        min_elevation: float = Query(default=10.0, ge=0, le=90),
        satellite: Optional[str] = Query(default=None),
    ):
        """Get upcoming satellite passes."""
        if not _scheduler:
            raise HTTPException(status_code=503, detail="Pass scheduler not available")

        if satellite:
            passes = _scheduler.next_passes(satellite, hours, min_elevation)
        else:
            passes = _scheduler.all_upcoming_passes(hours, min_elevation)

        return {
            "count": len(passes),
            "hours_ahead": hours,
            "min_elevation": min_elevation,
            "observer": {
                "lat": _scheduler.observer_lat,
                "lon": _scheduler.observer_lon,
                "alt": _scheduler.observer_alt,
            },
            "passes": [p.to_dict() for p in passes],
        }

    @router.get("/passes/next")
    async def get_next_pass(
        satellite: Optional[str] = Query(default=None),
    ):
        """Get the next satellite pass."""
        if not _scheduler:
            raise HTTPException(status_code=503, detail="Pass scheduler not available")

        if satellite:
            p = _scheduler.next_pass(satellite)
        else:
            passes = _scheduler.all_upcoming_passes(48.0, 10.0)
            p = passes[0] if passes else None

        if p is None:
            return {"pass": None, "eta_seconds": None}

        eta = _scheduler.time_to_next_pass(p.satellite_name)

        return {
            "pass": p.to_dict(),
            "eta_seconds": eta,
            "eta_minutes": round(eta / 60, 1) if eta else None,
        }

    @router.get("/passes/{satellite}")
    async def get_satellite_passes(
        satellite: str,
        hours: float = Query(default=24.0, ge=1, le=168),
        min_elevation: float = Query(default=10.0, ge=0, le=90),
        include_doppler: bool = Query(default=False),
    ):
        """Get passes for a specific satellite."""
        if not _scheduler:
            raise HTTPException(status_code=503, detail="Pass scheduler not available")

        passes = _scheduler.next_passes(satellite, hours, min_elevation)

        if include_doppler:
            for p in passes:
                p.doppler_profile = _scheduler.doppler_profile(p)

        return {
            "satellite": satellite,
            "count": len(passes),
            "passes": [p.to_dict() for p in passes],
        }

    @router.get("/duty_cycle")
    async def get_duty_cycle():
        """Get current ISM duty cycle budget."""
        if _duty_cycle_tracker is None:
            return {
                "budget_s": 36.0,
                "used_s": 0.0,
                "remaining_s": 36.0,
                "utilization_pct": 0.0,
            }

        return {
            "budget_s": _duty_cycle_tracker.budget_s,
            "used_s": round(_duty_cycle_tracker.used_airtime_s(), 2),
            "remaining_s": round(_duty_cycle_tracker.remaining_s(), 2),
            "utilization_pct": round(_duty_cycle_tracker.utilization_pct(), 1),
        }

    @router.get("/satellites")
    async def list_satellites():
        """List all loaded satellites."""
        if not _scheduler:
            raise HTTPException(status_code=503, detail="Pass scheduler not available")

        return {
            "count": len(_scheduler.satellites),
            "satellites": _scheduler.list_satellites(),
        }
