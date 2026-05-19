"""
OpenOrbitLink Voice Transport — Voice Message DTN Transport Layer

Handles chunking, reassembly, sequencing, and transport of voice messages
over DTN/LoRa store-and-forward paths.

Voice messages are encoded by the native codec pipeline (Codec2/Lyra) and
chunked into LoRa-compatible frames (≤80 bytes). This module manages:
  - Voice message metadata generation
  - Chunk creation and serialization
  - Reassembly from received chunks
  - Missing chunk detection and partial playback
  - Integration with DTN BundleStore
"""

from __future__ import annotations

import struct
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from .packet import OpenOrbitLinkPacket, PayloadType, TransmitBand


# ── Voice Wire Format Constants ──────────────────────────────────────────────

VOICE_MAGIC = 0x564D              # "VM" — Voice Message magic
VOICE_HEADER_SIZE = 10            # Bytes in voice chunk header
LORA_MAX_FRAME = 80               # Maximum LoRa payload (ISM duty-safe)
VOICE_MAX_PAYLOAD = LORA_MAX_FRAME - VOICE_HEADER_SIZE  # 70 bytes


# ── Codec Mode IDs (matching native codec_interface.h) ───────────────────────

class VoiceCodecMode(IntEnum):
    """Codec mode identifiers — must match native OolCodecMode enum."""
    CODEC2_700C  = 0x10
    CODEC2_1200  = 0x11
    CODEC2_1300  = 0x12
    CODEC2_1600  = 0x13
    CODEC2_2400  = 0x14
    CODEC2_3200  = 0x15
    LYRA_3200    = 0x20
    LYRA_6000    = 0x21
    LYRA_9200    = 0x22


# ── Codec Properties ────────────────────────────────────────────────────────

CODEC_PROPERTIES = {
    VoiceCodecMode.CODEC2_700C: {"bitrate": 700,  "frame_ms": 40, "frame_bytes": 4,  "lora_safe": True},
    VoiceCodecMode.CODEC2_1200: {"bitrate": 1200, "frame_ms": 40, "frame_bytes": 6,  "lora_safe": True},
    VoiceCodecMode.CODEC2_1300: {"bitrate": 1300, "frame_ms": 40, "frame_bytes": 7,  "lora_safe": True},
    VoiceCodecMode.CODEC2_1600: {"bitrate": 1600, "frame_ms": 40, "frame_bytes": 8,  "lora_safe": True},
    VoiceCodecMode.CODEC2_2400: {"bitrate": 2400, "frame_ms": 20, "frame_bytes": 6,  "lora_safe": False},
    VoiceCodecMode.CODEC2_3200: {"bitrate": 3200, "frame_ms": 20, "frame_bytes": 8,  "lora_safe": False},
    VoiceCodecMode.LYRA_3200:   {"bitrate": 3200, "frame_ms": 20, "frame_bytes": 8,  "lora_safe": False},
    VoiceCodecMode.LYRA_6000:   {"bitrate": 6000, "frame_ms": 20, "frame_bytes": 15, "lora_safe": False},
    VoiceCodecMode.LYRA_9200:   {"bitrate": 9200, "frame_ms": 20, "frame_bytes": 23, "lora_safe": False},
}


# ── Voice Chunk Flags ────────────────────────────────────────────────────────

class VoiceChunkFlags(IntEnum):
    NONE           = 0x00
    FIRST_CHUNK    = 0x01
    LAST_CHUNK     = 0x02
    FEC_ATTACHED   = 0x04
    ENHANCED       = 0x08
    DTX_SILENCE    = 0x10
    PRIORITY_SOS   = 0x20
    ENCRYPTED      = 0x40


# ── Voice Chunk ──────────────────────────────────────────────────────────────

@dataclass
class VoiceChunk:
    """
    One LoRa-sized chunk of a voice message.

    Wire format (10-byte header + payload):
    ┌────────┬───────┬──────┬──────┬───────┬──────────────┐
    │ MAGIC  │MSG_ID │SEQ_NO│FLAGS │CODEC  │ PAYLOAD      │
    │ 2 byte │4 byte │2 byte│1 byte│1 byte │ ≤70 bytes    │
    └────────┴───────┴──────┴──────┴───────┴──────────────┘
    """
    message_id: int
    sequence_num: int
    flags: int
    codec_mode: VoiceCodecMode
    payload: bytes
    frame_count: int = 0

    @property
    def is_first(self) -> bool:
        return bool(self.flags & VoiceChunkFlags.FIRST_CHUNK)

    @property
    def is_last(self) -> bool:
        return bool(self.flags & VoiceChunkFlags.LAST_CHUNK)

    @property
    def wire_size(self) -> int:
        return VOICE_HEADER_SIZE + len(self.payload)

    def serialize(self) -> bytes:
        """Serialize to wire format."""
        header = struct.pack(">HIHBB",
                             VOICE_MAGIC,
                             self.message_id & 0xFFFFFFFF,
                             self.sequence_num & 0xFFFF,
                             self.flags & 0xFF,
                             int(self.codec_mode) & 0xFF)
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['VoiceChunk']:
        """Deserialize from wire format."""
        if len(data) < VOICE_HEADER_SIZE:
            return None

        magic, msg_id, seq_num, flags, codec = struct.unpack(
            ">HIHBB", data[:VOICE_HEADER_SIZE])

        if magic != VOICE_MAGIC:
            return None

        try:
            codec_mode = VoiceCodecMode(codec)
        except ValueError:
            return None

        payload = data[VOICE_HEADER_SIZE:]

        return cls(
            message_id=msg_id,
            sequence_num=seq_num,
            flags=flags,
            codec_mode=codec_mode,
            payload=payload,
        )


# ── Voice Message Metadata ───────────────────────────────────────────────────

@dataclass
class VoiceMessageMeta:
    """
    Metadata for a complete voice message.
    Sent as a VOICE_META packet before or alongside chunks.
    """
    message_id: int
    codec_mode: VoiceCodecMode
    total_chunks: int
    total_frames: int
    duration_ms: int
    sample_rate: int = 8000
    sender_id: str = ""
    recipient_id: str = ""       # Empty for broadcast
    timestamp: float = field(default_factory=time.time)

    def serialize(self) -> bytes:
        """Serialize metadata to bytes."""
        return struct.pack(">IBBHHHI",
                           self.message_id & 0xFFFFFFFF,
                           int(self.codec_mode),
                           self.total_chunks & 0xFF,
                           self.total_frames & 0xFFFF,
                           self.duration_ms & 0xFFFF,
                           self.sample_rate & 0xFFFF,
                           int(self.timestamp) & 0xFFFFFFFF)

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['VoiceMessageMeta']:
        """Deserialize metadata from bytes."""
        if len(data) < 16:
            return None
        msg_id, codec, chunks, frames, dur_ms, sr, ts = struct.unpack(
            ">IBBHHHI", data[:16])
        try:
            codec_mode = VoiceCodecMode(codec)
        except ValueError:
            return None
        return cls(
            message_id=msg_id,
            codec_mode=codec_mode,
            total_chunks=chunks,
            total_frames=frames,
            duration_ms=dur_ms,
            sample_rate=sr,
            timestamp=float(ts),
        )


# ── Voice Chunker ────────────────────────────────────────────────────────────

def frames_per_chunk(codec_mode: VoiceCodecMode) -> int:
    """How many codec frames fit in one LoRa chunk payload."""
    props = CODEC_PROPERTIES.get(codec_mode)
    if not props:
        return 0
    return VOICE_MAX_PAYLOAD // props["frame_bytes"]


def chunk_voice_message(
    encoded_frames: list[bytes],
    codec_mode: VoiceCodecMode,
    message_id: Optional[int] = None,
) -> tuple[VoiceMessageMeta, list[VoiceChunk]]:
    """
    Split encoded voice frames into LoRa-compatible chunks.

    Args:
        encoded_frames: List of encoded audio frame bytes
        codec_mode: Codec mode used for encoding
        message_id: Optional message ID (auto-generated if None)

    Returns:
        Tuple of (metadata, list of chunks)
    """
    if not encoded_frames:
        raise ValueError("No frames to chunk")

    if message_id is None:
        message_id = int(uuid.uuid4().int & 0xFFFFFFFF)

    props = CODEC_PROPERTIES.get(codec_mode)
    if not props:
        raise ValueError(f"Unknown codec mode: {codec_mode}")

    frame_bytes = props["frame_bytes"]
    fpc = VOICE_MAX_PAYLOAD // frame_bytes
    if fpc <= 0:
        raise ValueError(f"Frame too large for LoRa: {frame_bytes} bytes")

    chunks: list[VoiceChunk] = []
    frame_idx = 0
    seq_num = 0

    while frame_idx < len(encoded_frames):
        batch_end = min(frame_idx + fpc, len(encoded_frames))
        batch = encoded_frames[frame_idx:batch_end]

        # Build payload from frames
        payload = b''.join(batch)

        # Set flags
        flags = VoiceChunkFlags.NONE
        if seq_num == 0:
            flags |= VoiceChunkFlags.FIRST_CHUNK
        if batch_end >= len(encoded_frames):
            flags |= VoiceChunkFlags.LAST_CHUNK

        chunks.append(VoiceChunk(
            message_id=message_id,
            sequence_num=seq_num,
            flags=flags,
            codec_mode=codec_mode,
            payload=payload,
            frame_count=len(batch),
        ))

        frame_idx = batch_end
        seq_num += 1

    # Calculate duration
    duration_ms = len(encoded_frames) * props["frame_ms"]

    meta = VoiceMessageMeta(
        message_id=message_id,
        codec_mode=codec_mode,
        total_chunks=len(chunks),
        total_frames=len(encoded_frames),
        duration_ms=duration_ms,
    )

    return meta, chunks


# ── Voice Reassembly Buffer ──────────────────────────────────────────────────

class VoiceReassemblyBuffer:
    """
    Reassembles voice chunks into a complete voice message.
    Handles out-of-order delivery, missing chunks, and partial playback.
    """

    def __init__(self, message_id: int, timeout_s: float = 60.0):
        self.message_id = message_id
        self.timeout_s = timeout_s
        self.chunks: dict[int, VoiceChunk] = {}
        self.expected_total: Optional[int] = None
        self.codec_mode: Optional[VoiceCodecMode] = None
        self.first_received_at: float = 0.0
        self.last_received_at: float = 0.0

    def add_chunk(self, chunk: VoiceChunk) -> bool:
        """
        Add a received chunk. Returns True if message is now complete.
        """
        if chunk.message_id != self.message_id:
            return False

        now = time.time()
        if self.first_received_at == 0:
            self.first_received_at = now
        self.last_received_at = now

        self.chunks[chunk.sequence_num] = chunk
        self.codec_mode = chunk.codec_mode

        # Track total from LAST_CHUNK flag
        if chunk.is_last:
            self.expected_total = chunk.sequence_num + 1

        return self.is_complete

    @property
    def is_complete(self) -> bool:
        """Check if all chunks have been received."""
        if self.expected_total is None:
            return False
        return len(self.chunks) >= self.expected_total

    @property
    def is_timed_out(self) -> bool:
        """Check if reassembly has timed out."""
        if self.first_received_at == 0:
            return False
        return (time.time() - self.first_received_at) > self.timeout_s

    @property
    def loss_rate(self) -> float:
        """Chunk loss rate (0.0 - 1.0)."""
        if self.expected_total is None or self.expected_total == 0:
            return 0.0
        missing = self.expected_total - len(self.chunks)
        return missing / self.expected_total

    @property
    def missing_chunks(self) -> list[int]:
        """List of missing chunk sequence numbers."""
        if self.expected_total is None:
            return []
        return [i for i in range(self.expected_total)
                if i not in self.chunks]

    def get_ordered_payloads(self) -> list[Optional[bytes]]:
        """
        Get payloads in sequence order.
        Missing chunks are represented as None for PLC.
        """
        if self.expected_total is None:
            # Use highest seq + 1
            if not self.chunks:
                return []
            max_seq = max(self.chunks.keys())
            total = max_seq + 1
        else:
            total = self.expected_total

        result: list[Optional[bytes]] = []
        for i in range(total):
            if i in self.chunks:
                result.append(self.chunks[i].payload)
            else:
                result.append(None)  # Missing — trigger PLC

        return result

    def get_stats(self) -> dict:
        """Get reassembly statistics."""
        return {
            "message_id": self.message_id,
            "received_chunks": len(self.chunks),
            "expected_total": self.expected_total,
            "is_complete": self.is_complete,
            "loss_rate": round(self.loss_rate, 4),
            "missing": self.missing_chunks,
            "codec_mode": self.codec_mode.name if self.codec_mode else None,
            "elapsed_s": round(self.last_received_at - self.first_received_at, 2)
                         if self.first_received_at else 0,
        }


# ── DTN Integration Helpers ──────────────────────────────────────────────────

def voice_chunks_to_bundles(
    meta: VoiceMessageMeta,
    chunks: list[VoiceChunk],
    device_id: bytes,
    transmit_band: TransmitBand = TransmitBand.ISM,
) -> list[OpenOrbitLinkPacket]:
    """
    Convert voice chunks into OpenOrbitLink packets for DTN queueing.

    Each chunk becomes a VOICE_CHUNK packet. A VOICE_META packet
    is prepended for receiver-side reassembly coordination.
    """
    packets: list[OpenOrbitLinkPacket] = []

    # 1. Metadata packet
    meta_packet = OpenOrbitLinkPacket(
        device_id=device_id,
        timestamp=int(time.time()),
        payload_type=PayloadType.VOICE_META,
        payload=meta.serialize(),
        transmit_band=transmit_band,
        sequence_num=0,
    )
    packets.append(meta_packet)

    # 2. Chunk packets
    for chunk in chunks:
        chunk_packet = OpenOrbitLinkPacket(
            device_id=device_id,
            timestamp=int(time.time()),
            payload_type=PayloadType.VOICE_CHUNK,
            payload=chunk.serialize(),
            transmit_band=transmit_band,
            sequence_num=chunk.sequence_num + 1,  # +1 for meta at seq 0
        )
        packets.append(chunk_packet)

    return packets


def estimate_lora_airtime(
    num_chunks: int,
    chunk_bytes: int = LORA_MAX_FRAME,
    effective_bps: float = 577.0,
    inter_packet_gap_ms: float = 100.0,
) -> float:
    """
    Estimate total LoRa airtime for voice chunks.

    Args:
        num_chunks: Number of chunks to transmit
        chunk_bytes: Average bytes per chunk
        effective_bps: Effective LoRa bitrate
        inter_packet_gap_ms: Gap between packets in ms

    Returns:
        Estimated airtime in seconds
    """
    tx_time_per_chunk = (chunk_bytes * 8) / effective_bps
    gap_time = (num_chunks - 1) * (inter_packet_gap_ms / 1000.0) if num_chunks > 1 else 0
    return num_chunks * tx_time_per_chunk + gap_time


def fits_duty_cycle(
    num_chunks: int,
    chunk_bytes: int = LORA_MAX_FRAME,
    used_airtime_s: float = 0.0,
    duty_cycle_budget_s: float = 36.0,
) -> bool:
    """Check if voice message fits in remaining ISM duty cycle budget."""
    airtime = estimate_lora_airtime(num_chunks, chunk_bytes)
    return (used_airtime_s + airtime) <= duty_cycle_budget_s
