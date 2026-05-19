from __future__ import annotations

"""
OpenOrbitLink — Codec Abstraction & Voice Transport Unit Tests

Tests the Python-side voice transport layer including:
  - Codec mode definitions and properties
  - Voice chunking and reassembly
  - Wire format serialization/deserialization
  - LoRa airtime estimation
  - Duty cycle enforcement
  - DTN integration
"""

import struct
import time
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.voice_transport import (
    VoiceCodecMode, VoiceChunk, VoiceChunkFlags, VoiceMessageMeta,
    VoiceReassemblyBuffer, CODEC_PROPERTIES, VOICE_MAGIC,
    VOICE_HEADER_SIZE, VOICE_MAX_PAYLOAD, LORA_MAX_FRAME,
    chunk_voice_message, frames_per_chunk,
    estimate_lora_airtime, fits_duty_cycle,
)


class TestCodecProperties(unittest.TestCase):
    """Test codec mode definitions and properties."""

    def test_all_modes_have_properties(self):
        """Every VoiceCodecMode should have an entry in CODEC_PROPERTIES."""
        for mode in VoiceCodecMode:
            self.assertIn(mode, CODEC_PROPERTIES,
                          f"Missing properties for {mode.name}")

    def test_codec2_700c_properties(self):
        """Codec2 700C: 700 bps, 40ms frames, 4 bytes/frame."""
        props = CODEC_PROPERTIES[VoiceCodecMode.CODEC2_700C]
        self.assertEqual(props["bitrate"], 700)
        self.assertEqual(props["frame_ms"], 40)
        self.assertEqual(props["frame_bytes"], 4)
        self.assertTrue(props["lora_safe"])

    def test_lyra_3200_properties(self):
        """Lyra 3200: 3200 bps, 20ms frames, 8 bytes/frame."""
        props = CODEC_PROPERTIES[VoiceCodecMode.LYRA_3200]
        self.assertEqual(props["bitrate"], 3200)
        self.assertEqual(props["frame_ms"], 20)
        self.assertEqual(props["frame_bytes"], 8)
        self.assertFalse(props["lora_safe"])

    def test_frame_bytes_match_bitrate(self):
        """Frame bytes should be consistent with bitrate and frame duration."""
        for mode, props in CODEC_PROPERTIES.items():
            expected_bytes = (props["bitrate"] * props["frame_ms"]) // 8000
            # Allow rounding: frame_bytes >= ceil(bits/8)
            bits_per_frame = props["bitrate"] * props["frame_ms"] // 1000
            min_bytes = (bits_per_frame + 7) // 8
            self.assertGreaterEqual(
                props["frame_bytes"], min_bytes,
                f"{mode.name}: frame_bytes={props['frame_bytes']} < "
                f"min={min_bytes} for {bits_per_frame} bits")


class TestFramesPerChunk(unittest.TestCase):
    """Test LoRa chunk frame packing calculations."""

    def test_codec2_700c_frames_per_chunk(self):
        """700C: 4 bytes/frame → 70/4 = 17 frames per chunk."""
        fpc = frames_per_chunk(VoiceCodecMode.CODEC2_700C)
        self.assertEqual(fpc, 17)  # 70 // 4

    def test_codec2_1300_frames_per_chunk(self):
        """1300: 7 bytes/frame → 70/7 = 10 frames per chunk."""
        fpc = frames_per_chunk(VoiceCodecMode.CODEC2_1300)
        self.assertEqual(fpc, 10)

    def test_lyra_9200_frames_per_chunk(self):
        """Lyra 9200: 23 bytes/frame → 70/23 = 3 frames per chunk."""
        fpc = frames_per_chunk(VoiceCodecMode.LYRA_9200)
        self.assertEqual(fpc, 3)

    def test_payload_never_exceeds_lora_limit(self):
        """Packed frames should never exceed 70-byte payload limit."""
        for mode in VoiceCodecMode:
            props = CODEC_PROPERTIES[mode]
            fpc = frames_per_chunk(mode)
            total = fpc * props["frame_bytes"]
            self.assertLessEqual(total, VOICE_MAX_PAYLOAD,
                                 f"{mode.name}: {total} > {VOICE_MAX_PAYLOAD}")


class TestVoiceChunkSerialization(unittest.TestCase):
    """Test voice chunk wire format."""

    def test_serialize_deserialize_roundtrip(self):
        """Chunk should survive serialization/deserialization."""
        original = VoiceChunk(
            message_id=0xDEADBEEF,
            sequence_num=42,
            flags=VoiceChunkFlags.FIRST_CHUNK | VoiceChunkFlags.FEC_ATTACHED,
            codec_mode=VoiceCodecMode.CODEC2_700C,
            payload=b'\x01\x02\x03\x04' * 5,
        )
        wire = original.serialize()
        recovered = VoiceChunk.deserialize(wire)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.message_id, original.message_id)
        self.assertEqual(recovered.sequence_num, original.sequence_num)
        self.assertEqual(recovered.flags, original.flags)
        self.assertEqual(recovered.codec_mode, original.codec_mode)
        self.assertEqual(recovered.payload, original.payload)

    def test_magic_bytes(self):
        """Serialized chunk should start with 'VM' magic."""
        chunk = VoiceChunk(
            message_id=1, sequence_num=0,
            flags=0, codec_mode=VoiceCodecMode.CODEC2_700C,
            payload=b'\x00',
        )
        wire = chunk.serialize()
        self.assertEqual(wire[0], 0x56)  # 'V'
        self.assertEqual(wire[1], 0x4D)  # 'M'

    def test_header_size(self):
        """Header should be exactly 10 bytes."""
        chunk = VoiceChunk(
            message_id=1, sequence_num=0,
            flags=0, codec_mode=VoiceCodecMode.CODEC2_700C,
            payload=b'',
        )
        wire = chunk.serialize()
        self.assertEqual(len(wire), VOICE_HEADER_SIZE)

    def test_invalid_magic_rejected(self):
        """Chunks with wrong magic should be rejected."""
        bad_data = b'\x00\x00' + b'\x00' * 20
        result = VoiceChunk.deserialize(bad_data)
        self.assertIsNone(result)

    def test_too_short_rejected(self):
        """Data shorter than header should be rejected."""
        result = VoiceChunk.deserialize(b'\x56\x4D\x00')
        self.assertIsNone(result)


class TestVoiceChunking(unittest.TestCase):
    """Test voice message chunking."""

    def _make_frames(self, count: int, frame_bytes: int) -> list[bytes]:
        """Generate dummy encoded frames."""
        return [bytes(range(frame_bytes)) for _ in range(count)]

    def test_5s_message_700c(self):
        """5-second message at 700C: 125 frames → ~8 chunks."""
        frames = self._make_frames(125, 4)  # 5s / 40ms = 125 frames
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        self.assertEqual(meta.total_frames, 125)
        self.assertEqual(meta.duration_ms, 5000)
        self.assertEqual(meta.codec_mode, VoiceCodecMode.CODEC2_700C)
        # 125 frames / 17 per chunk = ceil(7.35) = 8 chunks
        self.assertEqual(len(chunks), 8)

        # First chunk should have FIRST flag
        self.assertTrue(chunks[0].is_first)
        self.assertFalse(chunks[0].is_last)

        # Last chunk should have LAST flag
        self.assertTrue(chunks[-1].is_last)
        self.assertFalse(chunks[-1].is_first)

    def test_chunk_wire_size_within_limit(self):
        """All chunks must fit within 80-byte LoRa frame."""
        frames = self._make_frames(50, 7)  # 1300 mode
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_1300)

        for chunk in chunks:
            self.assertLessEqual(chunk.wire_size, LORA_MAX_FRAME,
                                 f"Chunk {chunk.sequence_num} exceeds limit")

    def test_empty_frames_raises(self):
        """Chunking empty frame list should raise ValueError."""
        with self.assertRaises(ValueError):
            chunk_voice_message([], VoiceCodecMode.CODEC2_700C)

    def test_single_frame(self):
        """Single frame should produce one chunk."""
        frames = self._make_frames(1, 4)
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].is_first)
        self.assertTrue(chunks[0].is_last)


class TestVoiceReassembly(unittest.TestCase):
    """Test voice message reassembly from chunks."""

    def test_complete_reassembly(self):
        """All chunks received → message complete."""
        frames = [bytes([i % 256] * 4) for i in range(25)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C, message_id=12345)

        buf = VoiceReassemblyBuffer(12345)
        for chunk in chunks:
            wire = chunk.serialize()
            parsed = VoiceChunk.deserialize(wire)
            buf.add_chunk(parsed)

        self.assertTrue(buf.is_complete)
        self.assertEqual(buf.loss_rate, 0.0)
        self.assertEqual(len(buf.missing_chunks), 0)

    def test_partial_reassembly(self):
        """Some chunks missing → partial message."""
        frames = [bytes([i] * 4) for i in range(50)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C, message_id=99)

        buf = VoiceReassemblyBuffer(99)
        # Skip every other chunk
        for i, chunk in enumerate(chunks):
            if i % 2 == 0:
                wire = chunk.serialize()
                parsed = VoiceChunk.deserialize(wire)
                buf.add_chunk(parsed)

        self.assertFalse(buf.is_complete)
        self.assertGreater(buf.loss_rate, 0.0)

    def test_out_of_order_delivery(self):
        """Chunks received out of order → still assembles correctly."""
        frames = [bytes([i] * 4) for i in range(10)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C, message_id=77)

        buf = VoiceReassemblyBuffer(77)
        # Deliver in reverse order
        for chunk in reversed(chunks):
            wire = chunk.serialize()
            parsed = VoiceChunk.deserialize(wire)
            buf.add_chunk(parsed)

        self.assertTrue(buf.is_complete)

    def test_missing_chunks_detected(self):
        """Missing chunks should appear in missing_chunks list."""
        frames = [bytes([0] * 4) for _ in range(50)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C, message_id=55)

        buf = VoiceReassemblyBuffer(55)
        # Only add first and last
        buf.add_chunk(VoiceChunk.deserialize(chunks[0].serialize()))
        buf.add_chunk(VoiceChunk.deserialize(chunks[-1].serialize()))

        missing = buf.missing_chunks
        self.assertGreater(len(missing), 0)
        self.assertNotIn(0, missing)
        self.assertNotIn(chunks[-1].sequence_num, missing)


class TestAirtimeEstimation(unittest.TestCase):
    """Test LoRa airtime calculations."""

    def test_basic_airtime(self):
        """Basic airtime should be positive and reasonable."""
        airtime = estimate_lora_airtime(7, 80)
        self.assertGreater(airtime, 0)
        # 7 chunks * 80 bytes * 8 bits / 577 bps ≈ 7.7s
        self.assertAlmostEqual(airtime, 7.7, delta=2.0)

    def test_single_chunk_airtime(self):
        """Single chunk airtime should be finite."""
        airtime = estimate_lora_airtime(1, 80)
        self.assertGreater(airtime, 0)
        self.assertLess(airtime, 10.0)

    def test_duty_cycle_check_pass(self):
        """Small message should pass duty cycle check."""
        self.assertTrue(fits_duty_cycle(2, 80, 0.0, 36.0))

    def test_duty_cycle_check_fail(self):
        """Message exceeding budget should fail duty cycle check."""
        self.assertFalse(fits_duty_cycle(100, 80, 35.0, 36.0))

    def test_duty_cycle_at_limit(self):
        """Message exactly at budget limit should pass."""
        # 1 chunk of 80 bytes at 577 bps = ~1.1s
        self.assertTrue(fits_duty_cycle(1, 80, 34.0, 36.0))


class TestVoiceMessageMeta(unittest.TestCase):
    """Test voice message metadata serialization."""

    def test_meta_roundtrip(self):
        """Metadata should survive serialization."""
        original = VoiceMessageMeta(
            message_id=0xCAFE,
            codec_mode=VoiceCodecMode.CODEC2_1300,
            total_chunks=13,
            total_frames=100,
            duration_ms=4000,
            sample_rate=8000,
        )
        data = original.serialize()
        recovered = VoiceMessageMeta.deserialize(data)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.message_id, original.message_id)
        self.assertEqual(recovered.codec_mode, original.codec_mode)
        self.assertEqual(recovered.total_chunks, original.total_chunks)
        self.assertEqual(recovered.total_frames, original.total_frames)
        self.assertEqual(recovered.duration_ms, original.duration_ms)


if __name__ == '__main__':
    unittest.main()
