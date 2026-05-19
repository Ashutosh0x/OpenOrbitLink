"""
OpenOrbitLink ISM Duty Cycle Rate Limiter.

Enforces the 1% ISM duty cycle rule on 868 MHz: max 36 seconds of TX time
per hour, shared across ALL users on a single LoRa node. Per-user fair-share
limits prevent any single user from monopolizing the shared resource.

Reference: ETSI EN 300 220, ECC Recommendation 70-03 Annex 1
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from .config import settings


@dataclass
class TxRecord:
    """A single transmission record."""
    user_id: int
    timestamp: float
    duration_seconds: float


@dataclass
class DutyCycleBudget:
    """Current duty cycle budget for a user or globally."""
    total_budget_seconds: float
    used_seconds: float
    remaining_seconds: float
    window_start: float
    window_end: float
    can_transmit: bool
    next_available_in_seconds: float = 0.0

    @property
    def usage_percent(self) -> float:
        if self.total_budget_seconds <= 0:
            return 100.0
        return (self.used_seconds / self.total_budget_seconds) * 100.0


class DutyCycleTracker:
    """
    Tracks ISM duty cycle compliance with a sliding 1-hour window.

    The 868 MHz ISM band allows 1% duty cycle = 36 seconds per hour.
    This is a SHARED constraint: one LoRa node serves all users.

    Allocation strategy:
    - Global limit: 36 seconds/hour total (hard regulatory cap)
    - Per-user fair share: global_limit / active_user_count
    - Minimum per-user: 2 seconds/hour (even with many users)
    """

    WINDOW_SECONDS = 3600.0  # 1-hour sliding window

    def __init__(
        self,
        max_tx_seconds_per_hour: float = settings.MAX_TX_SECONDS_PER_HOUR,
        min_per_user_seconds: float = 2.0,
    ):
        self.max_tx_seconds = max_tx_seconds_per_hour
        self.min_per_user_seconds = min_per_user_seconds
        self._records: List[TxRecord] = []
        self._lock = threading.Lock()

    def _prune_expired(self, now: float | None = None) -> None:
        """Remove records older than the sliding window."""
        now = now or time.time()
        cutoff = now - self.WINDOW_SECONDS
        self._records = [r for r in self._records if r.timestamp >= cutoff]

    def _global_used(self, now: float | None = None) -> float:
        """Total TX seconds used globally in the current window."""
        now = now or time.time()
        self._prune_expired(now)
        return sum(r.duration_seconds for r in self._records)

    def _user_used(self, user_id: int, now: float | None = None) -> float:
        """TX seconds used by a specific user in the current window."""
        now = now or time.time()
        self._prune_expired(now)
        return sum(
            r.duration_seconds for r in self._records if r.user_id == user_id
        )

    def _active_user_count(self, now: float | None = None) -> int:
        """Number of distinct users who transmitted in the current window."""
        now = now or time.time()
        self._prune_expired(now)
        users = {r.user_id for r in self._records}
        return max(len(users), 1)  # At least 1 for division

    def _per_user_budget(self, now: float | None = None) -> float:
        """Fair-share TX budget per user."""
        active = self._active_user_count(now)
        fair_share = self.max_tx_seconds / max(active, 1)
        return max(fair_share, self.min_per_user_seconds)

    def can_transmit(
        self,
        user_id: int,
        estimated_duration_seconds: float,
        now: float | None = None,
    ) -> bool:
        """Check if a transmission is allowed under duty cycle rules."""
        now = now or time.time()
        with self._lock:
            self._prune_expired(now)

            # Global hard limit
            global_used = self._global_used(now)
            if global_used + estimated_duration_seconds > self.max_tx_seconds:
                return False

            # Per-user fair share
            user_used = self._user_used(user_id, now)
            user_budget = self._per_user_budget(now)
            if user_used + estimated_duration_seconds > user_budget:
                return False

            return True

    def record_transmission(
        self,
        user_id: int,
        duration_seconds: float,
        now: float | None = None,
    ) -> None:
        """Record a completed transmission."""
        now = now or time.time()
        with self._lock:
            self._records.append(
                TxRecord(
                    user_id=user_id,
                    timestamp=now,
                    duration_seconds=duration_seconds,
                )
            )

    def get_budget(self, user_id: int, now: float | None = None) -> DutyCycleBudget:
        """Get the current duty cycle budget for a user."""
        now = now or time.time()
        with self._lock:
            self._prune_expired(now)
            global_used = self._global_used(now)
            user_used = self._user_used(user_id, now)
            user_budget = self._per_user_budget(now)

            global_remaining = max(0.0, self.max_tx_seconds - global_used)
            user_remaining = max(0.0, user_budget - user_used)
            effective_remaining = min(global_remaining, user_remaining)

            # Estimate when budget will free up
            next_available = 0.0
            if effective_remaining <= 0 and self._records:
                oldest = min(r.timestamp for r in self._records)
                next_available = max(0.0, (oldest + self.WINDOW_SECONDS) - now)

            return DutyCycleBudget(
                total_budget_seconds=min(user_budget, self.max_tx_seconds),
                used_seconds=user_used,
                remaining_seconds=effective_remaining,
                window_start=now - self.WINDOW_SECONDS,
                window_end=now,
                can_transmit=effective_remaining > 0,
                next_available_in_seconds=next_available,
            )

    def get_global_status(self, now: float | None = None) -> dict:
        """Get global duty cycle status for the station."""
        now = now or time.time()
        with self._lock:
            self._prune_expired(now)
            global_used = self._global_used(now)
            return {
                "max_tx_seconds_per_hour": self.max_tx_seconds,
                "used_seconds": round(global_used, 2),
                "remaining_seconds": round(
                    max(0.0, self.max_tx_seconds - global_used), 2
                ),
                "usage_percent": round(
                    (global_used / self.max_tx_seconds) * 100.0, 1
                )
                if self.max_tx_seconds > 0
                else 100.0,
                "active_users": self._active_user_count(now),
                "total_transmissions": len(self._records),
                "ism_band": "868 MHz",
                "duty_cycle_limit": f"{settings.ISM_DUTY_CYCLE_PERCENT}%",
            }


# ─── Singleton ──────────────────────────────────────────────────────────

duty_cycle_tracker = DutyCycleTracker()
