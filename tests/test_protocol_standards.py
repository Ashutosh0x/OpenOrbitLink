from __future__ import annotations

import pytest

from protocol.aprs import (
    build_ax25_ui_frame,
    decode_ax25_ui_frame,
    parse_aprs_info,
)
from protocol.bpv7 import (
    BPv7ValidationError,
    Bundle as BPv7Bundle,
    BundleControlFlags,
    CRCType,
    CreationTimestamp,
    EndpointID,
    PrimaryBlock,
    payload_block,
)
from protocol.packet import OpenOrbitLinkPacket, OpenOrbitLinkProtocol, PayloadType
from protocol.packet import TransmitBand
from protocol.license import CallsignValidator, LicenseGate
from protocol.fossa import FossaFrame, FossaFrameError, packet_payload_to_fossa_frames
from ground_station.tinygs_client import TinyGSClient
from simulation.link_budget import LinkBudgetParams, TxPath, analyze_throughput, compute_link_budget
from security import BandType, EncryptionPolicyError
from security.bpsec import (
    AbstractSecurityBlock,
    BPSecValidationError,
    SecurityResult,
    bcb_block,
    bib_block,
    security_processing_order,
    validate_security_blocks,
)
from protocol.bpv7 import BlockControlFlags


def _primary(source=None, crc_type=CRCType.CRC16_X25, flags=0):
    node = source or EndpointID.ipn(1, 0)
    return PrimaryBlock(
        destination=EndpointID.ipn(2, 1),
        source_node=node,
        report_to=node,
        creation_timestamp=CreationTimestamp(832_550_400_000, 1),
        lifetime_ms=60_000,
        bundle_control_flags=flags,
        crc_type=crc_type,
    )


def test_bpv7_bundle_emits_indefinite_cbor_with_crc_blocks():
    bundle = BPv7Bundle(_primary(), [payload_block(b"hello")])

    encoded = bundle.encode()

    assert encoded[0] == 0x9F
    assert encoded[-1] == 0xFF
    assert bundle.primary.encode() in encoded
    assert bundle.payload_block().block_number == 1


def test_bpv7_rejects_anonymous_bundle_status_report_requests():
    primary = _primary(
        source=EndpointID.null(),
        flags=(
            BundleControlFlags.BUNDLE_MUST_NOT_BE_FRAGMENTED
            | BundleControlFlags.REPORT_DELIVERY
        ),
    )
    bundle = BPv7Bundle(primary, [payload_block(b"anonymous")])

    with pytest.raises(BPv7ValidationError, match="anonymous bundles"):
        bundle.validate()


def test_bpsec_bib_can_replace_primary_crc_requirement():
    source = EndpointID.ipn(1, 0)
    asb = AbstractSecurityBlock(
        target_blocks=[0],
        security_context_id=1,
        security_source=source,
        security_results=[[SecurityResult(1, b"mac")]],
    )
    bib = bib_block(2, asb)
    bundle = BPv7Bundle(_primary(source=source, crc_type=CRCType.NONE), [bib, payload_block(b"payload")])

    validate_security_blocks(bundle)
    assert security_processing_order(bundle) == [bib]


def test_bpsec_requires_payload_bcb_replication_and_bib_encryption():
    source = EndpointID.ipn(1, 0)
    bib_asb = AbstractSecurityBlock(
        target_blocks=[1],
        security_context_id=1,
        security_source=source,
        security_results=[[SecurityResult(1, b"plain-integrity")]],
    )
    bcb_asb = AbstractSecurityBlock(
        target_blocks=[1, 2],
        security_context_id=1,
        security_source=source,
        security_results=[[SecurityResult(1, b"tag")], [SecurityResult(1, b"tag2")]],
    )
    bib = bib_block(2, bib_asb)
    bcb = bcb_block(
        3,
        bcb_asb,
        flags=int(BlockControlFlags.REPLICATE_IN_EVERY_FRAGMENT),
    )
    payload = payload_block(b"ciphertext")
    bundle = BPv7Bundle(_primary(source=source), [bib, bcb, payload])

    validate_security_blocks(bundle)
    assert security_processing_order(bundle) == [bcb, bib]

    unsafe_bcb = bcb_block(3, bcb_asb, flags=0)
    unsafe_bundle = BPv7Bundle(_primary(source=source), [bib, unsafe_bcb, payload])
    with pytest.raises(BPSecValidationError, match="payload"):
        validate_security_blocks(unsafe_bundle)

    with pytest.raises(BPSecValidationError, match="amateur radio"):
        validate_security_blocks(bundle, band=BandType.AMATEUR)


def test_ax25_ui_frame_roundtrip_with_fcs_and_aprs_position():
    raw = build_ax25_ui_frame(
        "VU2ASH",
        "RS0ISS",
        b"=2836.83N/07712.54E-OpenOrbitLink Ground Station Delhi",
        digipeaters=["WIDE1-1"],
    )

    frame = decode_ax25_ui_frame(raw)
    aprs = parse_aprs_info(frame.information)
    position = aprs.fields["position"]

    assert frame.fcs_valid is True
    assert frame.source.display == "VU2ASH"
    assert frame.destination.display == "RS0ISS"
    assert frame.digipeaters[0].display == "WIDE1-1"
    assert aprs.kind == "position"
    assert position.symbol_code == "-"
    assert abs(position.latitude.value - 28.613833) < 0.0001
    assert abs(position.longitude.value - 77.209) < 0.0001


def test_aprs_compressed_position_course_speed_and_message_ack():
    aprs = parse_aprs_info("=/5L!!<*e7>7P[")
    position = aprs.fields["position"]

    assert position.compressed is True
    assert abs(position.latitude.value - 49.5) < 0.01
    assert abs(position.longitude.value + 72.75) < 0.01
    assert position.extension["course_deg"] == 88
    assert abs(position.extension["speed_knots"] - 36.2) < 0.2

    ack = parse_aprs_info(":KB2ICI-14:ack003")
    assert ack.kind == "message_ack"
    assert ack.fields["message_id"] == "003"


def test_openorbitlink_packet_rejects_malformed_lengths_and_hop_overflow():
    proto = OpenOrbitLinkProtocol("standards-test")
    packet = proto.create_text_message("tight framing")
    raw = packet.serialize()

    assert OpenOrbitLinkPacket.deserialize(raw + b"\x00") is None

    invalid_type = bytearray(raw)
    invalid_type[14] = 0xFF
    # Rebuild CRC so the type check is what fails.
    from protocol.packet import crc16_ccitt

    crc = crc16_ccitt(bytes(invalid_type[:-2]))
    invalid_type[-2:] = crc.to_bytes(2, "big")
    assert OpenOrbitLinkPacket.deserialize(bytes(invalid_type)) is None

    relay = OpenOrbitLinkPacket(
        device_id=packet.device_id,
        timestamp=packet.timestamp,
        payload_type=PayloadType.TEXT,
        payload=b"x",
        hop_count=9,
        ttl=10,
    )
    assert relay.relay_copy().hop_count == 10
    with pytest.raises(ValueError, match="hop limit"):
        relay.relay_copy().relay_copy()


def test_packet_band_field_and_encryption_guard():
    proto = OpenOrbitLinkProtocol("band-policy")
    plain_ham = proto.create_text_message("plain APRS-like payload", band=TransmitBand.AMATEUR)
    parsed = OpenOrbitLinkPacket.deserialize(plain_ham.serialize())

    assert parsed is not None
    assert parsed.transmit_band == TransmitBand.AMATEUR
    assert parsed.is_encrypted is False

    encrypted_ism = proto.create_encrypted_packet(PayloadType.TEXT, b"ciphertext", band=TransmitBand.ISM)
    assert OpenOrbitLinkPacket.deserialize(encrypted_ism.serialize()).is_encrypted is True

    with pytest.raises(EncryptionPolicyError, match="amateur radio"):
        proto.create_encrypted_packet(PayloadType.TEXT, b"ciphertext", band=TransmitBand.AMATEUR)


def test_license_gate_blocks_unlicensed_amateur_tx():
    assert CallsignValidator.normalize("vu2ash-7") == "VU2ASH-7"
    assert LicenseGate("VU2ASH", country="IN", license_confirmed=True).authorize(TransmitBand.AMATEUR).allowed

    decision = LicenseGate("VU2ASH", country="IN", license_confirmed=False).authorize(TransmitBand.AMATEUR)
    assert decision.allowed is False
    assert "confirm" in decision.reason

    encrypted = LicenseGate("VU2ASH", country="IN", license_confirmed=True).authorize(
        TransmitBand.AMATEUR,
        encrypted=True,
    )
    assert encrypted.allowed is False
    assert "amateur radio" in encrypted.reason


def test_link_budget_marks_rtl_sdr_receive_only_and_accounts_overhead():
    rx_only = compute_link_budget(LinkBudgetParams(tx_path=TxPath.RTL_SDR_RX_ONLY))
    assert rx_only["tx_capable"] is False
    assert rx_only["is_viable"] is False
    assert "receive-only" in rx_only["reason"]

    throughput = analyze_throughput(payload_bytes=256, raw_bitrate_bps=700.0)
    assert throughput.total_tx_bytes == 311
    assert 3.5 < throughput.tx_time_seconds < 3.6
    assert throughput.effective_payload_bps < 700.0


def test_fossa_frames_fit_payload_limit_and_base64_roundtrip():
    frames = packet_payload_to_fossa_frames(PayloadType.TEXT, b"x" * 140, encrypted=True)
    assert len(frames) == 3
    assert all(len(frame.encode()) <= 80 for frame in frames)

    encoded = frames[0].to_base64()
    decoded = FossaFrame.from_base64(encoded)
    assert decoded.payload == frames[0].payload
    assert decoded.flags & 1

    broken = bytearray(frames[0].encode())
    broken[-1] ^= 0xFF
    with pytest.raises(FossaFrameError, match="CRC"):
        FossaFrame.decode(bytes(broken))


def test_tinygs_client_dry_run_uses_base64_payload():
    client = TinyGSClient(base_url="https://example.invalid/api", bearer_token="token")
    result = client.transmit_frame("station-1", b"\x01\x02\x03", dry_run=True)

    assert result.ok is True
    assert result.status_code == 0
    assert result.response["frame"] == "AQID"
    assert client.frame_from_base64(result.response["frame"]) == b"\x01\x02\x03"
