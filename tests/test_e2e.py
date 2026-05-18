"""
OpenOrbitLink End-to-End Test Suite

Tests the complete pipeline: packet creation, encoding,
channel simulation, decoding, and delivery verification.
"""
from __future__ import annotations

import os
import sys
import time
import struct
import tempfile

import numpy as np

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol.packet import OpenOrbitLinkPacket, OpenOrbitLinkProtocol, PayloadType, TransmitBand, crc16_ccitt
from protocol.dtn import DTNEngine, BundleStore, BundleState
from protocol.mesh import MeshNode, MeshRouter, NodeCapability
from protocol.fossa import packet_payload_to_fossa_frames
from ai.orbital_predictor import OrbitalPredictor, GroundStation
from ai.speech_enhance import Codec2Wrapper, SatellitePLC, VoiceFrame, SAMPLES_PER_FRAME
from simulation.link_budget import TxPath, analyze_throughput, compute_link_budget, LinkBudgetParams, simulate_awgn_channel
from scripts.fetch_tle import classify_tle_age, parse_tle_records
from security import EncryptionPolicyError


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print("  PASS: {}".format(name))

    def fail(self, name, reason=""):
        self.failed += 1
        self.errors.append((name, reason))
        print("  FAIL: {}: {}".format(name, reason))

    def summary(self):
        total = self.passed + self.failed
        print("\n" + "=" * 50)
        print("Results: {}/{} passed, {} failed".format(self.passed, total, self.failed))
        if self.errors:
            print("\nFailures:")
            for name, reason in self.errors:
                print("  - {}: {}".format(name, reason))
        print("=" * 50)
        return self.failed == 0


def run_protocol_packet(results):
    """Test packet serialization and deserialization."""
    print("\n-- Protocol Packet Tests --")

    proto = OpenOrbitLinkProtocol("test-device-001")

    # Test text message
    pkt = proto.create_text_message("Hello OpenOrbitLink!")
    raw = pkt.serialize()
    parsed = OpenOrbitLinkPacket.deserialize(raw)
    if parsed and parsed.payload == b"Hello OpenOrbitLink!":
        results.ok("Text message round-trip")
    else:
        results.fail("Text message round-trip", "Payload mismatch")

    # Test SOS packet
    sos = proto.create_sos(28.6139, 77.2090, "Need help!")
    raw = sos.serialize()
    parsed = OpenOrbitLinkPacket.deserialize(raw)
    if parsed and parsed.payload_type == PayloadType.SOS:
        lat, lon = struct.unpack('>ff', parsed.payload[:8])
        if abs(lat - 28.6139) < 0.001 and abs(lon - 77.2090) < 0.001:
            results.ok("SOS packet with GPS")
        else:
            results.fail("SOS packet with GPS", "GPS mismatch: {}, {}".format(lat, lon))
    else:
        results.fail("SOS packet with GPS", "Parse failed")

    # Test beacon
    beacon = proto.create_beacon()
    raw = beacon.serialize()
    parsed = OpenOrbitLinkPacket.deserialize(raw)
    if parsed and parsed.payload_type == PayloadType.BEACON:
        results.ok("Beacon packet")
    else:
        results.fail("Beacon packet")

    # Test CRC corruption detection
    raw = pkt.serialize()
    corrupted = bytearray(raw)
    corrupted[-1] ^= 0xFF
    parsed = OpenOrbitLinkPacket.deserialize(bytes(corrupted))
    if parsed is None:
        results.ok("CRC corruption detection")
    else:
        results.fail("CRC corruption detection", "Corrupted packet not rejected")

    # Test device ID generation
    id1 = OpenOrbitLinkPacket.generate_device_id("device-A")
    id2 = OpenOrbitLinkPacket.generate_device_id("device-B")
    id1_dup = OpenOrbitLinkPacket.generate_device_id("device-A")
    if id1 != id2 and id1 == id1_dup and len(id1) == 6:
        results.ok("Device ID generation")
    else:
        results.fail("Device ID generation")

    # Test band-aware encryption guard
    ham_plain = proto.create_text_message("plain ham payload", band=TransmitBand.AMATEUR)
    parsed = OpenOrbitLinkPacket.deserialize(ham_plain.serialize())
    if parsed and parsed.transmit_band == TransmitBand.AMATEUR and not parsed.is_encrypted:
        results.ok("Band field round-trip (amateur plaintext)")
    else:
        results.fail("Band field round-trip")

    try:
        proto.create_encrypted_packet(PayloadType.TEXT, b"ciphertext", band=TransmitBand.AMATEUR)
        results.fail("Encrypted amateur guard", "Encrypted amateur packet was allowed")
    except EncryptionPolicyError:
        results.ok("Encrypted amateur guard")

    carrier = proto.create_text_message("carrier NTN gateway candidate", band=TransmitBand.CARRIER_NTN)
    parsed = OpenOrbitLinkPacket.deserialize(carrier.serialize())
    if parsed and parsed.transmit_band == TransmitBand.CARRIER_NTN:
        results.ok("Carrier NTN band field")
    else:
        results.fail("Carrier NTN band field")


def run_codec2_voice(results):
    """Test Codec2 voice encoding/decoding pipeline."""
    print("\n-- Voice Codec Tests --")

    codec = Codec2Wrapper()

    # Generate test audio (440Hz sine wave)
    t = np.arange(SAMPLES_PER_FRAME) / 8000.0
    sine_wave = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

    # Encode
    encoded = codec.encode(sine_wave)
    if len(encoded) == 4 and encoded != b'\x00\x00\x00\x00':
        results.ok("Codec2 encode (700bps simulation)")
    else:
        results.fail("Codec2 encode", "Got {} bytes".format(len(encoded)))

    # Decode
    decoded = codec.decode(encoded)
    if len(decoded) == SAMPLES_PER_FRAME:
        results.ok("Codec2 decode (320 samples)")
    else:
        results.fail("Codec2 decode", "Got {} samples".format(len(decoded)))

    # Test PLC
    plc = SatellitePLC(codec)
    for i in range(5):
        frame = VoiceFrame(
            sequence_number=i,
            encoded_bits=codec.encode(sine_wave),
            pcm_samples=sine_wave.copy(),
        )
        plc.process_frame(frame, i)

    reconstructed = plc.process_frame(None, 5)
    if reconstructed.is_reconstructed and len(reconstructed.pcm_samples) == SAMPLES_PER_FRAME:
        results.ok("PLC gap reconstruction (confidence={:.1f})".format(reconstructed.confidence))
    else:
        results.fail("PLC gap reconstruction")


def run_orbital_predictor(results):
    """Test satellite pass prediction."""
    print("\n-- Orbital Predictor Tests --")

    observer = GroundStation(28.6139, 77.2090, 216.0)
    predictor = OrbitalPredictor(observer)

    norad_id = predictor.load_tle(
        "ISS (ZARYA)",
        "1 25544U 98067A   26136.50000000  .00016717  00000-0  10270-3 0  9005",
        "2 25544  51.6400 100.0000 0006000  80.0000 280.0000 15.49000000400005",
    )

    if norad_id == 25544:
        results.ok("TLE loading (ISS)")
    else:
        results.fail("TLE loading", "Got NORAD {}".format(norad_id))

    from datetime import datetime, timezone
    now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    passes = predictor.predict_passes(norad_id, now, duration_hours=24.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if len(passes) > 0:
        results.ok("Pass prediction ({} passes in {:.1f}ms)".format(len(passes), elapsed_ms))
    else:
        results.fail("Pass prediction", "No passes found")

    if elapsed_ms < 500:
        results.ok("Prediction speed ({:.1f}ms < 500ms)".format(elapsed_ms))
    else:
        results.fail("Prediction speed", "{:.1f}ms exceeds 500ms".format(elapsed_ms))

    if passes:
        p = passes[0]
        if 0 <= p.quality_score <= 1.0 and p.duration_seconds > 0:
            results.ok("Pass quality scoring (score={:.2f})".format(p.quality_score))
        else:
            results.fail("Pass quality scoring")


def run_link_budget(results):
    """Test link budget calculations."""
    print("\n-- Link Budget Tests --")

    params = LinkBudgetParams(
        frequency_hz=145.8e6,
        satellite_altitude_km=408,
        elevation_deg=30,
    )
    result = compute_link_budget(params)

    if result["slant_range_km"] > 0:
        results.ok("Slant range ({:.0f} km)".format(result["slant_range_km"]))
    else:
        results.fail("Slant range calculation")

    if result["fspl_db"] > 100:
        results.ok("Free space path loss ({:.1f} dB)".format(result["fspl_db"]))
    else:
        results.fail("Free space path loss")

    params_high = LinkBudgetParams(elevation_deg=90)
    result_high = compute_link_budget(params_high)
    if result_high["slant_range_km"] < result["slant_range_km"]:
        results.ok("Elevation vs range relationship")
    else:
        results.fail("Elevation vs range relationship")

    rx_only = compute_link_budget(LinkBudgetParams(tx_path=TxPath.RTL_SDR_RX_ONLY))
    if not rx_only["tx_capable"] and not rx_only["is_viable"]:
        results.ok("RTL-SDR marked receive-only")
    else:
        results.fail("RTL-SDR receive-only guard")

    carrier_ntn = compute_link_budget(LinkBudgetParams(tx_path=TxPath.CARRIER_NTN))
    if not carrier_ntn["tx_capable"] and "Carrier-managed" in carrier_ntn["reason"]:
        results.ok("Carrier NTN marked closed uplink")
    else:
        results.fail("Carrier NTN closed uplink guard")

    throughput = analyze_throughput(256, raw_bitrate_bps=700.0)
    if throughput.total_tx_bytes == 311 and throughput.effective_payload_bps < 700:
        results.ok("Throughput overhead accounting")
    else:
        results.fail("Throughput overhead accounting")


def run_dtn_engine(results):
    """Test DTN store-and-forward engine."""
    print("\n-- DTN Engine Tests --")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        proto = OpenOrbitLinkProtocol("test-dtn-device")
        dtn = DTNEngine(proto, db_path=db_path)

        id1 = dtn.queue_text("Hello DTN!")
        id2 = dtn.queue_sos(28.6, 77.2, "Emergency!")
        id3 = dtn.queue_text("Second message")

        stats = dtn.get_stats()
        if stats.get("QUEUED", 0) == 3:
            results.ok("Bundle queuing (3 bundles)")
        else:
            results.fail("Bundle queuing", "Expected 3 QUEUED, got {}".format(stats))

        pending = dtn.store.get_pending()
        if pending and pending[0]["payload_type"] == int(PayloadType.SOS):
            results.ok("Priority ordering (SOS first)")
        else:
            results.fail("Priority ordering")

        dtn.receive_ack(id1)
        stats = dtn.get_stats()
        if stats.get("DELIVERED", 0) == 1:
            results.ok("ACK processing")
        else:
            results.fail("ACK processing")

        try:
            dtn.queue_text("secret ham packet", band=TransmitBand.AMATEUR, encrypt=True)
            results.fail("DTN encrypted amateur block")
        except EncryptionPolicyError:
            results.ok("DTN encrypted amateur block")
    finally:
        os.unlink(db_path)


def run_regulatory_and_fossa(results):
    """Test license-aware routing, FOSSA frames, and TLE age helpers."""
    print("\n-- Regulatory/FOSSA/TLE Tests --")

    router = MeshRouter(b"ABCDEF")
    blocked = router.find_best_route(satellite_visible=True, transmit_band=TransmitBand.AMATEUR)
    if blocked and blocked.startswith("blocked:"):
        results.ok("Mesh blocks unlicensed amateur route")
    else:
        results.fail("Mesh blocks unlicensed amateur route", str(blocked))

    licensed = MeshRouter(
        b"ABCDEF",
        capabilities=int(NodeCapability.SDR_TRANSMIT | NodeCapability.SATELLITE_DIRECT),
        callsign="VU2ASH",
        license_confirmed=True,
    )
    route = licensed.find_best_route(satellite_visible=True, transmit_band=TransmitBand.AMATEUR)
    if route == "satellite_direct":
        results.ok("Mesh allows licensed amateur direct route")
    else:
        results.fail("Mesh allows licensed amateur direct route", str(route))

    frames = packet_payload_to_fossa_frames(PayloadType.TEXT, b"x" * 140, encrypted=True)
    if len(frames) == 3 and all(len(frame.encode()) <= 80 for frame in frames):
        results.ok("FOSSA 80-byte frame fragmentation")
    else:
        results.fail("FOSSA 80-byte frame fragmentation")

    tle = "\n".join([
        "ISS (ZARYA)",
        "1 25544U 98067A   26136.50000000  .00016717  00000-0  10270-3 0  9005",
        "2 25544  51.6400 100.0000 0006000  80.0000 280.0000 15.49000000400005",
    ])
    from datetime import datetime, timezone
    records = parse_tle_records(tle, now=datetime(2026, 5, 17, tzinfo=timezone.utc))
    if records and records[0].staleness == "fresh" and classify_tle_age(8.0) == "stale":
        results.ok("TLE age metadata helpers")
    else:
        results.fail("TLE age metadata helpers")


def run_channel_simulation(results):
    """Test RF channel simulation."""
    print("\n-- Channel Simulation Tests --")

    bits = np.random.randint(0, 2, 1000)
    signal = 2.0 * bits - 1.0 + 0j

    noisy = simulate_awgn_channel(signal, snr_db=20.0)
    detected = (np.real(noisy) > 0).astype(int)
    ber = np.mean(detected != bits)
    if ber < 0.01:
        results.ok("AWGN channel (BER={:.4f} at 20dB)".format(ber))
    else:
        results.fail("AWGN channel", "BER={:.4f} too high".format(ber))

    noisy_low = simulate_awgn_channel(signal, snr_db=0.0)
    detected_low = (np.real(noisy_low) > 0).astype(int)
    ber_low = np.mean(detected_low != bits)
    if ber_low > 0.01:
        results.ok("AWGN low-SNR degradation (BER={:.4f} at 0dB)".format(ber_low))
    else:
        results.fail("AWGN low-SNR", "Expected errors at 0dB SNR")


def main():
    print("=" * 50)
    print("OpenOrbitLink -- End-to-End Test Suite")
    print("=" * 50)

    results = TestResults()

    run_protocol_packet(results)
    run_codec2_voice(results)
    run_orbital_predictor(results)
    run_link_budget(results)
    run_dtn_engine(results)
    run_regulatory_and_fossa(results)
    run_channel_simulation(results)

    success = results.summary()
    sys.exit(0 if success else 1)


def test_e2e_suite():
    results = TestResults()
    run_protocol_packet(results)
    run_codec2_voice(results)
    run_orbital_predictor(results)
    run_link_budget(results)
    run_dtn_engine(results)
    run_regulatory_and_fossa(results)
    run_channel_simulation(results)
    assert results.failed == 0, results.errors


if __name__ == "__main__":
    main()
