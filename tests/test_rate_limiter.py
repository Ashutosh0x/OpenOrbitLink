"""
OpenOrbitLink ISM Duty Cycle Rate Limiter Tests.

Tests the 1% duty cycle enforcement, per-user fair share allocation,
sliding window expiry, and global shared limits.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.rate_limiter import DutyCycleTracker, DutyCycleBudget


def test_initial_budget():
    """Fresh tracker should have full budget available."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    budget = tracker.get_budget(user_id=1)

    assert budget.remaining_seconds == 36.0, f"Expected 36.0, got {budget.remaining_seconds}"
    assert budget.used_seconds == 0.0
    assert budget.can_transmit == True
    print("  PASS: Initial budget is full (36.0s)")


def test_single_transmission():
    """Recording a TX should reduce the budget."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    assert tracker.can_transmit(1, 5.0, now=now), "Should be able to transmit 5s"
    tracker.record_transmission(1, 5.0, now=now)

    budget = tracker.get_budget(1, now=now)
    assert budget.used_seconds == 5.0, f"Expected 5.0 used, got {budget.used_seconds}"
    assert budget.remaining_seconds == 31.0, f"Expected 31.0 remaining, got {budget.remaining_seconds}"
    print("  PASS: Single TX reduces budget correctly")


def test_duty_cycle_exhaustion():
    """Should block TX when duty cycle is exhausted."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    # Use up most of the budget
    tracker.record_transmission(1, 35.0, now=now)

    # Should allow 1s more
    assert tracker.can_transmit(1, 1.0, now=now), "Should allow 1s more"
    # Should block 2s
    assert not tracker.can_transmit(1, 2.0, now=now), "Should block 2s (only 1s left)"

    # Use the last second
    tracker.record_transmission(1, 1.0, now=now)
    assert not tracker.can_transmit(1, 0.1, now=now), "Should block when fully exhausted"

    budget = tracker.get_budget(1, now=now)
    assert budget.can_transmit == False
    assert budget.remaining_seconds == 0.0
    print("  PASS: Duty cycle exhaustion blocks TX")


def test_global_shared_limit():
    """Global limit applies across ALL users."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    # User 1 uses 20s
    tracker.record_transmission(1, 20.0, now=now)
    # User 2 uses 15s
    tracker.record_transmission(2, 15.0, now=now)

    # Global total: 35s. Only 1s left globally.
    assert not tracker.can_transmit(3, 2.0, now=now), "Global limit should block user 3"

    global_status = tracker.get_global_status(now=now)
    assert global_status["used_seconds"] == 35.0
    assert global_status["remaining_seconds"] == 1.0
    assert global_status["active_users"] == 2
    print("  PASS: Global shared limit enforced across users")


def test_per_user_fair_share():
    """Per-user budget should be fair-shared among active users."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    # Two active users: each gets 36/2 = 18s
    tracker.record_transmission(1, 1.0, now=now)
    tracker.record_transmission(2, 1.0, now=now)

    budget_1 = tracker.get_budget(1, now=now)
    budget_2 = tracker.get_budget(2, now=now)

    # Each user's fair share should be ~18s (36/2)
    assert budget_1.total_budget_seconds <= 18.0, f"Expected <=18.0, got {budget_1.total_budget_seconds}"
    assert budget_2.total_budget_seconds <= 18.0, f"Expected <=18.0, got {budget_2.total_budget_seconds}"
    print("  PASS: Per-user fair share allocation")


def test_sliding_window_expiry():
    """Old transmissions should expire after 1 hour."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    # Record TX 2 hours ago
    old_time = now - 7200  # 2 hours ago
    tracker.record_transmission(1, 30.0, now=old_time)

    # Current budget should be full (old TX expired)
    budget = tracker.get_budget(1, now=now)
    assert budget.used_seconds == 0.0, f"Expected 0.0 (expired), got {budget.used_seconds}"
    assert budget.remaining_seconds == 36.0, f"Expected 36.0, got {budget.remaining_seconds}"
    assert budget.can_transmit == True
    print("  PASS: Sliding window expires old transmissions")


def test_minimum_per_user_budget():
    """Even with many users, each gets at least min_per_user_seconds."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0, min_per_user_seconds=2.0)
    now = time.time()

    # Simulate 20 active users
    for uid in range(1, 21):
        tracker.record_transmission(uid, 0.1, now=now)

    # Fair share = 36/20 = 1.8s, but min is 2.0s
    budget = tracker.get_budget(1, now=now)
    assert budget.total_budget_seconds >= 2.0, f"Expected >=2.0 min, got {budget.total_budget_seconds}"
    print("  PASS: Minimum per-user budget enforced (2.0s)")


def test_global_status_report():
    """Global status should report correct aggregate stats."""
    tracker = DutyCycleTracker(max_tx_seconds_per_hour=36.0)
    now = time.time()

    tracker.record_transmission(1, 5.0, now=now)
    tracker.record_transmission(2, 3.0, now=now)
    tracker.record_transmission(1, 2.0, now=now)

    status = tracker.get_global_status(now=now)
    assert status["used_seconds"] == 10.0
    assert status["remaining_seconds"] == 26.0
    assert status["active_users"] == 2
    assert status["total_transmissions"] == 3
    assert status["ism_band"] == "868 MHz"
    assert status["duty_cycle_limit"] == "1.0%"
    print("  PASS: Global status report accurate")


def main():
    print("=" * 50)
    print("OpenOrbitLink Rate Limiter Test Suite")
    print("=" * 50)

    test_initial_budget()
    test_single_transmission()
    test_duty_cycle_exhaustion()
    test_global_shared_limit()
    test_per_user_fair_share()
    test_sliding_window_expiry()
    test_minimum_per_user_budget()
    test_global_status_report()

    print("\n" + "=" * 50)
    print("All rate limiter tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    main()
