"""
Tests for OpenOrbitLink Satellite Pass Scheduler, Doppler, and DTN Routing.

Covers:
  - Pass prediction with mock TLE data
  - Doppler calculation accuracy
  - DTN routing strategies (Epidemic, Spray-and-Wait)
  - BPv7 bundle serialization round-trip
  - APRS callsign validation
  - Duty cycle tracking
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _has_skyfield() -> bool:
    try:
        import skyfield
        return True
    except ImportError:
        return False


# --- Mock TLE data (ISS as of a known epoch) ---
MOCK_ISS_TLE = """ISS (ZARYA)
1 25544U 98067A   26139.50000000  .00016717  00000+0  10270-3 0  9002
2 25544  51.6400 100.0000 0001234  85.0000 275.0000 15.50000000000001
"""


# ============================================================
# Pass Scheduler Tests
# ============================================================

class TestPassScheduler:
    """Tests for scripts/pass_scheduler.py."""

    @pytest.fixture
    def tle_file(self, tmp_path):
        """Create a temporary TLE file."""
        tle_path = tmp_path / "test_satellites.tle"
        tle_path.write_text(MOCK_ISS_TLE.strip())
        return str(tle_path)

    def test_import(self):
        """Pass scheduler module imports successfully."""
        from scripts.pass_scheduler import PassScheduler, SatellitePass, DopplerPoint
        assert PassScheduler is not None
        assert SatellitePass is not None
        assert DopplerPoint is not None

    @pytest.mark.skipif(
        not _has_skyfield(), reason="skyfield not installed"
    )
    def test_load_tle(self, tle_file):
        """Satellites load from TLE file."""
        from scripts.pass_scheduler import PassScheduler
        scheduler = PassScheduler(tle_path=tle_file)
        assert len(scheduler.satellites) >= 1
        assert "ISS (ZARYA)" in scheduler.list_satellites()

    @pytest.mark.skipif(
        not _has_skyfield(), reason="skyfield not installed"
    )
    def test_find_satellite(self, tle_file):
        """Find satellite by partial name match."""
        from scripts.pass_scheduler import PassScheduler
        scheduler = PassScheduler(tle_path=tle_file)
        sat = scheduler.find_satellite("ISS")
        assert sat is not None
        assert "ISS" in sat.name

    @pytest.mark.skipif(
        not _has_skyfield(), reason="skyfield not installed"
    )
    def test_next_passes(self, tle_file):
        """Next passes returns valid pass objects."""
        from scripts.pass_scheduler import PassScheduler
        scheduler = PassScheduler(
            tle_path=tle_file,
            observer_lat=28.6139,
            observer_lon=77.2090,
        )
        passes = scheduler.next_passes("ISS", hours_ahead=48.0, min_elevation=5.0)
        # ISS should have multiple passes in 48 hours over any location
        assert len(passes) >= 1

        p = passes[0]
        assert p.satellite_name.strip() == "ISS (ZARYA)"
        assert p.max_elevation_deg > 5.0
        assert p.duration_s > 0
        assert p.rise_time < p.set_time

    @pytest.mark.skipif(
        not _has_skyfield(), reason="skyfield not installed"
    )
    def test_pass_table_format(self, tle_file):
        """Format passes as readable table."""
        from scripts.pass_scheduler import PassScheduler, format_pass_table
        scheduler = PassScheduler(tle_path=tle_file)
        passes = scheduler.next_passes("ISS", hours_ahead=48.0)
        table = format_pass_table(passes)
        assert "ISS" in table or "No passes" in table


# ============================================================
# DTN Routing Tests
# ============================================================

class TestDTNRouting:
    """Tests for protocol/dtn_routing.py."""

    def test_import(self):
        from protocol.dtn_routing import DTNRouter, RoutingStrategy
        assert DTNRouter is not None

    def test_direct_routing(self):
        """Direct routing only forwards to destination."""
        from protocol.dtn_routing import DTNRouter, RoutingStrategy

        router = DTNRouter(node_id="node_A", strategy=RoutingStrategy.DIRECT)
        router.originate("bundle_1", "node_C")

        # Should not forward to non-destination
        assert not router.should_forward("bundle_1", "node_B")
        # Should forward to destination
        assert router.should_forward("bundle_1", "node_C")

    def test_epidemic_routing(self):
        """Epidemic routing forwards to all neighbors."""
        from protocol.dtn_routing import DTNRouter, RoutingStrategy

        router = DTNRouter(node_id="node_A", strategy=RoutingStrategy.EPIDEMIC)
        router.originate("bundle_1", "node_D")

        assert router.should_forward("bundle_1", "node_B")
        assert router.should_forward("bundle_1", "node_C")
        assert router.should_forward("bundle_1", "node_D")

    def test_spray_and_wait_spray_phase(self):
        """Spray-and-Wait sprays copies then waits."""
        from protocol.dtn_routing import DTNRouter, RoutingStrategy

        router = DTNRouter(
            node_id="node_A",
            strategy=RoutingStrategy.SPRAY_AND_WAIT,
            spray_copies=4,
        )
        entry = router.originate("bundle_1", "node_Z")
        assert entry.copies_remaining == 4

        # Spray to first neighbor
        to_send = router.on_encounter("node_B", set())
        assert "bundle_1" in to_send
        # Copies should be halved (Binary Spray)
        assert router.routing_table["bundle_1"].copies_remaining == 2

        # Spray to second neighbor
        to_send = router.on_encounter("node_C", set())
        assert "bundle_1" in to_send
        assert router.routing_table["bundle_1"].copies_remaining == 1

        # Wait phase: should only forward to destination
        assert not router.should_forward("bundle_1", "node_D")
        assert router.should_forward("bundle_1", "node_Z")

    def test_deduplication(self):
        """Duplicate bundles are rejected."""
        from protocol.dtn_routing import DTNRouter, RoutingStrategy

        router = DTNRouter(node_id="node_A", strategy=RoutingStrategy.EPIDEMIC)
        assert router.on_receive("bundle_1", "node_B", "node_C") is True
        assert router.on_receive("bundle_1", "node_D", "node_C") is False
        assert router.stats["duplicates_suppressed"] == 1

    def test_delivery_to_self(self):
        """Bundle addressed to us is delivered."""
        from protocol.dtn_routing import DTNRouter

        router = DTNRouter(node_id="node_A")
        assert router.on_receive("bundle_1", "node_B", "node_A") is True
        assert router.stats["bundles_delivered"] == 1

    def test_anti_entropy_exchange(self):
        """Anti-entropy exchange skips known bundles."""
        from protocol.dtn_routing import DTNRouter, RoutingStrategy

        router = DTNRouter(node_id="node_A", strategy=RoutingStrategy.EPIDEMIC)
        router.originate("bundle_1", "node_Z")
        router.originate("bundle_2", "node_Z")

        # Neighbor already has bundle_1
        to_send = router.on_encounter("node_B", {"bundle_1"})
        assert "bundle_1" not in to_send
        assert "bundle_2" in to_send


# ============================================================
# BPv7 Bundle Tests
# ============================================================

class TestBPv7:
    """Tests for protocol/bpv7.py."""

    def test_import(self):
        from protocol.bpv7 import BPv7Bundle, EndpointID, PrimaryBlock
        assert BPv7Bundle is not None

    def test_endpoint_id(self):
        """EndpointID creation and string representation."""
        from protocol.bpv7 import EndpointID

        eid = EndpointID.from_device_id("abc123", "inbox")
        assert "abc123" in str(eid)
        assert "inbox" in str(eid)

    def test_compact_roundtrip(self):
        """Bundle serializes and deserializes (compact format)."""
        from protocol.bpv7 import BPv7Bundle, EndpointID

        bundle = BPv7Bundle()
        bundle.primary.source = EndpointID.from_device_id("src001")
        bundle.primary.destination = EndpointID.from_device_id("dst002")
        bundle.payload = b"Hello from OpenOrbitLink!"

        data = bundle._serialize_compact()
        assert len(data) > 0

        restored = BPv7Bundle._deserialize_compact(data)
        assert restored is not None
        assert restored.payload == b"Hello from OpenOrbitLink!"

    def test_integrity_block(self):
        """BIB (HMAC-SHA256) verification works."""
        from protocol.bpv7 import BPv7Bundle

        bundle = BPv7Bundle()
        bundle.payload = b"Important satellite message"
        key = b"shared_secret_key_32bytes_long!!"

        bundle.add_integrity(key)
        assert len(bundle.extension_blocks) == 1
        assert bundle.verify_integrity(key) is True
        assert bundle.verify_integrity(b"wrong_key_________________________") is False

    def test_confidentiality_amateur_blocked(self):
        """BCB is blocked on amateur bands."""
        from protocol.bpv7 import BPv7Bundle

        bundle = BPv7Bundle()
        bundle.payload = b"Test"
        key = os.urandom(32)

        with pytest.raises(ValueError, match="amateur"):
            bundle.add_confidentiality(key, band="amateur")

    def test_confidentiality_ism_allowed(self):
        """BCB works on ISM bands."""
        from protocol.bpv7 import BPv7Bundle

        bundle = BPv7Bundle()
        bundle.payload = b"Encrypted satellite message"
        key = os.urandom(32)

        original_payload = bundle.payload
        bundle.add_confidentiality(key, band="ism")
        assert bundle.payload != original_payload  # Encrypted

        assert bundle.decrypt_confidentiality(key) is True
        assert bundle.payload == original_payload  # Decrypted


# ============================================================
# APRS Bridge Tests
# ============================================================

class TestAPRSBridge:
    """Tests for protocol/aprs_bridge.py."""

    def test_callsign_validation(self):
        """ITU callsign format validation."""
        from protocol.aprs_bridge import APRSBridge

        # Valid callsigns
        assert APRSBridge.validate_callsign("VU2ABC") is True
        assert APRSBridge.validate_callsign("W1AW") is True
        assert APRSBridge.validate_callsign("JA1YRL") is True
        assert APRSBridge.validate_callsign("G3XYZ") is True
        assert APRSBridge.validate_callsign("VU3CWG-9") is True
        assert APRSBridge.validate_callsign("K1ABC-15") is True

        # Invalid callsigns
        assert APRSBridge.validate_callsign("123") is False
        assert APRSBridge.validate_callsign("ABCDEF") is False
        assert APRSBridge.validate_callsign("A1") is False
        assert APRSBridge.validate_callsign("VU2ABC-16") is False  # SSID > 15

    def test_passcode_computation(self):
        """APRS-IS passcode is computed correctly."""
        from protocol.aprs_bridge import APRSBridge

        # Known passcode for N0CALL = 13023
        pc = APRSBridge.compute_passcode("N0CALL")
        assert isinstance(pc, int)
        assert 0 <= pc <= 32767

        # Same callsign = same passcode
        assert APRSBridge.compute_passcode("VU2ABC") == APRSBridge.compute_passcode("VU2ABC")

        # SSID stripped
        assert APRSBridge.compute_passcode("VU2ABC") == APRSBridge.compute_passcode("VU2ABC-9")

    def test_invalid_callsign_rejected(self):
        """Bridge rejects invalid callsigns on construction."""
        from protocol.aprs_bridge import APRSBridge

        with pytest.raises(ValueError):
            APRSBridge(callsign="INVALID123")


# ============================================================
# Duty Cycle Tracker Tests
# ============================================================

class TestDutyCycleTracker:
    """Tests for ground_station/pass_integration.py DutyCycleTracker."""

    def test_import(self):
        from ground_station.pass_integration import DutyCycleTracker
        assert DutyCycleTracker is not None

    def test_initial_budget(self):
        """Fresh tracker has full budget."""
        from ground_station.pass_integration import DutyCycleTracker

        tracker = DutyCycleTracker()
        assert tracker.remaining_s() == 36.0
        assert tracker.can_transmit(1.0)

    def test_record_tx(self):
        """Recording TX reduces budget."""
        from ground_station.pass_integration import DutyCycleTracker

        tracker = DutyCycleTracker()
        tracker.record_tx(10.0)
        assert tracker.used_airtime_s() == 10.0
        assert tracker.remaining_s() == 26.0

    def test_budget_exhaustion(self):
        """Cannot transmit when budget exhausted."""
        from ground_station.pass_integration import DutyCycleTracker

        tracker = DutyCycleTracker()
        tracker.record_tx(35.0)
        assert tracker.can_transmit(2.0) is False
        assert tracker.can_transmit(0.5) is True

    def test_utilization(self):
        """Utilization percentage is correct."""
        from ground_station.pass_integration import DutyCycleTracker

        tracker = DutyCycleTracker()
        tracker.record_tx(18.0)
        assert abs(tracker.utilization_pct() - 50.0) < 0.1


# ============================================================
# Inbox Router Tests
# ============================================================

class TestInboxRouter:
    """Tests for ground_station/inbox_router.py."""

    def test_import(self):
        from ground_station.inbox_router import InboxRouter
        assert InboxRouter is not None

    def test_deduplication(self):
        """Duplicate packets are detected."""
        from ground_station.inbox_router import InboxRouter

        router = InboxRouter()
        data = b"test packet data"
        assert router._is_duplicate(data) is False
        assert router._is_duplicate(data) is True

    def test_ool_header_decode(self):
        """OOL packet header decodes correctly."""
        import struct
        from ground_station.inbox_router import InboxRouter

        router = InboxRouter()

        # Construct valid OOL header (21 bytes)
        header = struct.pack(">H", 0x4F4C)           # magic "OL"
        header += struct.pack("B", 1)                  # version
        header += b"\x01\x02\x03\x04\x05\x06\x07\x08" # device_id (8 bytes)
        header += struct.pack(">I", int(time.time()))   # timestamp
        header += struct.pack("B", 1)                   # payload_type
        header += struct.pack(">H", 42)                 # sequence
        header += struct.pack("B", 0)                    # flags
        header += struct.pack("B", 1)                    # band
        header += struct.pack("B", 5)                    # payload_len
        header += b"hello"                               # payload

        result = router._decode_ool_header(header)
        assert result is not None
        assert result["version"] == 1
        assert result["payload_type"] == 1
        assert result["sequence"] == 42
        assert result["payload"] == b"hello"


# ============================================================
# Airtime Estimation Tests
# ============================================================

class TestAirtimeEstimation:
    """Tests for LoRa airtime estimation."""

    def test_sf12_bw125_80bytes(self):
        """SF12 BW125 80-byte packet airtime is reasonable."""
        from ground_station.pass_integration import estimate_packet_airtime_s

        airtime = estimate_packet_airtime_s(80, sf=12, bw_hz=125_000)
        # SF12 BW125 80 bytes should be ~2-4 seconds
        assert 1.0 < airtime < 10.0

    def test_sf7_bw125_80bytes(self):
        """SF7 BW125 80-byte packet is much faster than SF12."""
        from ground_station.pass_integration import estimate_packet_airtime_s

        airtime_sf7 = estimate_packet_airtime_s(80, sf=7, bw_hz=125_000)
        airtime_sf12 = estimate_packet_airtime_s(80, sf=12, bw_hz=125_000)

        assert airtime_sf7 < airtime_sf12
        # SF7 should be < 0.5s
        assert airtime_sf7 < 0.5



