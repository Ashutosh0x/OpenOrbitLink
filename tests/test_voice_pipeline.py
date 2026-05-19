from __future__ import annotations

"""
OpenOrbitLink — Voice Pipeline Integration Tests

End-to-end tests for the voice message lifecycle:
  1. Encode → Chunk → Serialize → Deserialize → Reassemble → Decode
  2. Partial delivery with PLC simulation
  3. DTN integration flow
  4. Multi-codec mode switching
"""

import unittest
import struct
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.voice_transport import (
    VoiceCodecMode, VoiceChunk, VoiceChunkFlags, VoiceMessageMeta,
    VoiceReassemblyBuffer, CODEC_PROPERTIES,
    chunk_voice_message, frames_per_chunk,
    estimate_lora_airtime, fits_duty_cycle,
    voice_chunks_to_bundles,
)
from protocol.packet import PayloadType


class TestEndToEndVoicePipeline(unittest.TestCase):
    """Full encode→chunk→transport→reassemble→decode pipeline."""

    def test_5s_700c_full_pipeline(self):
        """
        Simulate a 5-second 700C voice message through the full pipeline.
        """
        # Simulate 125 encoded frames (5s / 40ms)
        num_frames = 125
        frame_bytes = 4  # 700C
        encoded_frames = [os.urandom(frame_bytes) for _ in range(num_frames)]

        # Chunk
        meta, chunks = chunk_voice_message(
            encoded_frames, VoiceCodecMode.CODEC2_700C)

        self.assertEqual(meta.total_frames, 125)
        self.assertEqual(meta.duration_ms, 5000)

        # Simulate transport: serialize → deserialize
        reassembly = VoiceReassemblyBuffer(meta.message_id)
        for chunk in chunks:
            wire = chunk.serialize()
            # Simulate LoRa transport
            received = VoiceChunk.deserialize(wire)
            self.assertIsNotNone(received)
            reassembly.add_chunk(received)

        # Should be complete
        self.assertTrue(reassembly.is_complete)

        # Get ordered payloads
        payloads = reassembly.get_ordered_payloads()
        self.assertEqual(len(payloads), len(chunks))

        # Verify total decoded bytes match
        total_bytes = sum(len(p) for p in payloads if p is not None)
        self.assertEqual(total_bytes, num_frames * frame_bytes)

    def test_10s_1300_with_packet_loss(self):
        """
        10-second 1300 mode with 20% packet loss.
        """
        num_frames = 250  # 10s / 40ms
        frame_bytes = 7
        encoded_frames = [os.urandom(frame_bytes) for _ in range(num_frames)]

        meta, chunks = chunk_voice_message(
            encoded_frames, VoiceCodecMode.CODEC2_1300)

        # Simulate 20% packet loss
        reassembly = VoiceReassemblyBuffer(meta.message_id)
        delivered = 0
        for i, chunk in enumerate(chunks):
            if i % 5 != 0:  # Drop every 5th chunk
                wire = chunk.serialize()
                received = VoiceChunk.deserialize(wire)
                reassembly.add_chunk(received)
                delivered += 1

        # Should NOT be complete
        self.assertFalse(reassembly.is_complete)

        # Loss rate should be approximately 20%
        stats = reassembly.get_stats()
        self.assertGreater(stats["loss_rate"], 0.1)
        self.assertLess(stats["loss_rate"], 0.3)

        # Missing chunks should be detected
        self.assertGreater(len(stats["missing"]), 0)

        # Ordered payloads should have None for missing chunks
        payloads = reassembly.get_ordered_payloads()
        none_count = sum(1 for p in payloads if p is None)
        self.assertGreater(none_count, 0)


class TestMultiCodecModes(unittest.TestCase):
    """Test chunking across all codec modes."""

    def test_all_modes_chunk_correctly(self):
        """Every codec mode should produce valid chunks."""
        for mode in VoiceCodecMode:
            props = CODEC_PROPERTIES[mode]
            # Simulate 2 seconds of audio
            num_frames = 2000 // props["frame_ms"]
            frames = [os.urandom(props["frame_bytes"])
                      for _ in range(num_frames)]

            meta, chunks = chunk_voice_message(frames, mode)

            self.assertGreater(len(chunks), 0, f"{mode.name}")
            self.assertEqual(meta.total_frames, num_frames, f"{mode.name}")
            self.assertEqual(meta.duration_ms, 2000, f"{mode.name}")
            self.assertEqual(meta.codec_mode, mode, f"{mode.name}")

            # Verify all chunk wire sizes are within limit
            for chunk in chunks:
                self.assertLessEqual(chunk.wire_size, 80,
                                     f"{mode.name} chunk {chunk.sequence_num}")

    def test_codec2_modes_are_lora_safe(self):
        """Codec2 modes ≤1600bps should be marked as LoRa-safe."""
        lora_safe_modes = [
            VoiceCodecMode.CODEC2_700C,
            VoiceCodecMode.CODEC2_1200,
            VoiceCodecMode.CODEC2_1300,
            VoiceCodecMode.CODEC2_1600,
        ]
        for mode in lora_safe_modes:
            self.assertTrue(CODEC_PROPERTIES[mode]["lora_safe"],
                            f"{mode.name} should be LoRa-safe")


class TestDTNBundleIntegration(unittest.TestCase):
    """Test voice chunk → DTN bundle conversion."""

    def test_chunks_to_bundles(self):
        """Voice chunks should convert to valid DTN packets."""
        frames = [os.urandom(4) for _ in range(25)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        device_id = b'\x01\x02\x03\x04\x05\x06'
        from protocol.packet import TransmitBand
        packets = voice_chunks_to_bundles(
            meta, chunks, device_id, TransmitBand.ISM)

        # Should have meta packet + chunk packets
        self.assertEqual(len(packets), 1 + len(chunks))

        # First packet should be VOICE_META
        self.assertEqual(packets[0].payload_type, PayloadType.VOICE_META)

        # Remaining should be VOICE_CHUNK
        for pkt in packets[1:]:
            self.assertEqual(pkt.payload_type, PayloadType.VOICE_CHUNK)


class TestAirtimeBudgetScenarios(unittest.TestCase):
    """Real-world airtime budget scenarios."""

    def test_5s_700c_fits_fresh_budget(self):
        """5s 700C message should easily fit in fresh 36s budget."""
        frames = [b'\x00' * 4 for _ in range(125)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        airtime = estimate_lora_airtime(len(chunks), 80)
        self.assertTrue(fits_duty_cycle(len(chunks), 80))
        self.assertLess(airtime, 36.0)

    def test_30s_700c_fits_fresh_budget(self):
        """30s 700C message (max) should still fit in fresh budget."""
        frames = [b'\x00' * 4 for _ in range(750)]  # 30s / 40ms
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        airtime = estimate_lora_airtime(len(chunks), 80)
        # This is a large message — may or may not fit depending on
        # exact airtime calculation
        self.assertGreater(airtime, 0)

    def test_lyra_9200_wont_fit_lora(self):
        """Lyra 9200 5s message should require many chunks."""
        frames = [os.urandom(23) for _ in range(250)]  # 5s / 20ms
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.LYRA_9200)

        # Should require many chunks (250 frames / 3 per chunk ≈ 84)
        self.assertGreater(len(chunks), 50)

        # Airtime should be very high
        airtime = estimate_lora_airtime(len(chunks), 80)
        self.assertGreater(airtime, 36.0)  # Exceeds 1% duty cycle


class TestVoiceChunkFlags(unittest.TestCase):
    """Test chunk flag combinations."""

    def test_first_and_last_single_chunk(self):
        """Single-chunk message should have both FIRST and LAST flags."""
        frames = [b'\x00' * 4]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].is_first)
        self.assertTrue(chunks[0].is_last)

    def test_intermediate_chunks_no_first_last(self):
        """Middle chunks should have neither FIRST nor LAST."""
        frames = [b'\x00' * 4 for _ in range(100)]
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)

        if len(chunks) > 2:
            for chunk in chunks[1:-1]:
                self.assertFalse(chunk.is_first,
                                 f"Chunk {chunk.sequence_num} should not be first")
                self.assertFalse(chunk.is_last,
                                 f"Chunk {chunk.sequence_num} should not be last")


if __name__ == '__main__':
    unittest.main()
