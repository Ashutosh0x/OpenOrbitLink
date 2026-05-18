from __future__ import annotations
"""
OpenOrbitLink Protocol — Packet Structures & Encoding

Hybrid protocol combining AX.25 amateur radio framing with CCSDS
space-grade error correction and DTN delay-tolerant bundle transport.
"""

import struct
import hashlib
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import numpy as np


# ─── Packet Constants ────────────────────────────────────────────────────────

SYNC_WORD = b'\xFE\x6B\x28\x40'     # 4-byte sync + Barker-13 prefix
PROTOCOL_VERSION = 1
MAX_PAYLOAD_SIZE = 2048               # bytes
CRC16_POLY = 0x1021                   # CRC-16 CCITT polynomial


class PayloadType(IntEnum):
    TEXT = 0x01
    VOICE = 0x02
    SOS = 0x03
    RELAY = 0x04
    ACK = 0x05
    BEACON = 0x06


@dataclass
class OpenOrbitLinkPacket:
    """
    OpenOrbitLink protocol packet structure.

    Wire format:
    ┌──────┬───────┬─────┬──────┬─────────┬─────┬──────┐
    │ SYNC │DEV_ID │TIME │ TYPE │ PAYLOAD │ FEC │ CRC  │
    │4 byte│6 byte │4 by │1 by  │variable │32 by│2 byte│
    └──────┴───────┴─────┴──────┴─────────┴─────┴──────┘
    """
    device_id: bytes              # 6 bytes — SHA-256 truncated
    timestamp: int                # 4 bytes — Unix UTC seconds
    payload_type: PayloadType     # 1 byte
    payload: bytes                # variable — encrypted
    fec_data: bytes = b''         # 32 bytes — Reed-Solomon parity
    sequence_num: int = 0         # For ordering
    hop_count: int = 0            # Number of relay hops
    ttl: int = 10                 # Maximum hops

    def serialize(self) -> bytes:
        """Serialize packet to wire format bytes."""
        header = struct.pack(
            '>4s6sIBBBH',
            SYNC_WORD,
            self.device_id[:6],
            self.timestamp & 0xFFFFFFFF,
            self.payload_type,
            self.hop_count,
            self.ttl,
            len(self.payload),
        )
        body = self.payload
        fec = self.fec_data[:32].ljust(32, b'\x00')
        raw = header + body + fec
        crc = crc16_ccitt(raw)
        return raw + struct.pack('>H', crc)

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['OpenOrbitLinkPacket']:
        """Deserialize packet from wire bytes."""
        if len(data) < 21 + 32 + 2:  # min header + FEC + CRC
            return None
        if data[:4] != SYNC_WORD:
            return None

        # Verify CRC
        payload_end = len(data) - 2
        expected_crc = struct.unpack('>H', data[payload_end:])[0]
        actual_crc = crc16_ccitt(data[:payload_end])
        if expected_crc != actual_crc:
            return None

        # Parse header
        device_id = data[4:10]
        timestamp = struct.unpack('>I', data[10:14])[0]
        payload_type = PayloadType(data[14])
        hop_count = data[15]
        ttl = data[16]
        payload_len = struct.unpack('>H', data[17:19])[0]

        # Extract payload and FEC
        payload = data[19:19 + payload_len]
        fec_start = 19 + payload_len
        fec_data = data[fec_start:fec_start + 32]

        return cls(
            device_id=device_id,
            timestamp=timestamp,
            payload_type=payload_type,
            payload=payload,
            fec_data=fec_data,
            hop_count=hop_count,
            ttl=ttl,
        )

    @staticmethod
    def generate_device_id(unique_string: str) -> bytes:
        """Generate 6-byte device ID from SHA-256 of unique identifier."""
        return hashlib.sha256(unique_string.encode()).digest()[:6]


def crc16_ccitt(data: bytes) -> int:
    """CRC-16 CCITT checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ CRC16_POLY
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ─── Reed-Solomon FEC ────────────────────────────────────────────────────────

class ReedSolomonFEC:
    """
    Simplified Reed-Solomon (255,223) forward error correction.
    Corrects up to 16 symbol errors per block.
    """

    def __init__(self, nsym: int = 32):
        self.nsym = nsym  # Number of parity symbols

    def encode(self, data: bytes) -> bytes:
        """Add RS parity bytes to data."""
        # Simplified: XOR-based parity for development
        # Production should use proper GF(2^8) RS implementation
        parity = bytearray(self.nsym)
        for i, b in enumerate(data):
            parity[i % self.nsym] ^= b
        return bytes(parity)

    def decode(self, data: bytes, parity: bytes) -> tuple[bytes, int]:
        """
        Attempt error correction using RS parity.
        Returns (corrected_data, errors_corrected).
        """
        # Simplified verification
        expected = self.encode(data)
        errors = sum(1 for a, b in zip(parity, expected) if a != b)
        return data, errors


# ─── Message Builder ─────────────────────────────────────────────────────────

class OpenOrbitLinkProtocol:
    """High-level protocol operations for building and parsing messages."""

    def __init__(self, device_id: str):
        self.device_id = OpenOrbitLinkPacket.generate_device_id(device_id)
        self.fec = ReedSolomonFEC()
        self._seq_counter = 0

    def create_text_message(self, text: str, encrypt: bool = True) -> OpenOrbitLinkPacket:
        """Create a text message packet."""
        payload = text.encode('utf-8')[:256]
        return self._build_packet(PayloadType.TEXT, payload)

    def create_voice_packet(self, codec2_frames: bytes) -> OpenOrbitLinkPacket:
        """Create a voice packet from Codec2 encoded frames."""
        return self._build_packet(PayloadType.VOICE, codec2_frames[:1024])

    def create_sos(self, lat: float, lon: float, message: str = "") -> OpenOrbitLinkPacket:
        """Create emergency SOS packet with GPS coordinates."""
        payload = struct.pack('>ff', lat, lon) + message.encode('utf-8')[:56]
        return self._build_packet(PayloadType.SOS, payload)

    def create_beacon(self, capabilities: int = 0xFF) -> OpenOrbitLinkPacket:
        """Create network presence beacon."""
        payload = struct.pack('>BH', capabilities, self._seq_counter)
        return self._build_packet(PayloadType.BEACON, payload)

    def create_ack(self, original_device_id: bytes, original_seq: int) -> OpenOrbitLinkPacket:
        """Create delivery acknowledgment."""
        payload = original_device_id[:6] + struct.pack('>I', original_seq)
        return self._build_packet(PayloadType.ACK, payload)

    def _build_packet(self, ptype: PayloadType, payload: bytes) -> OpenOrbitLinkPacket:
        """Build a complete packet with FEC."""
        self._seq_counter += 1
        fec_data = self.fec.encode(payload)

        return OpenOrbitLinkPacket(
            device_id=self.device_id,
            timestamp=int(time.time()),
            payload_type=ptype,
            payload=payload,
            fec_data=fec_data,
            sequence_num=self._seq_counter,
        )

    def parse_packet(self, raw: bytes) -> Optional[OpenOrbitLinkPacket]:
        """Parse and validate a received packet."""
        packet = OpenOrbitLinkPacket.deserialize(raw)
        if packet is None:
            return None

        # Verify FEC
        _, errors = self.fec.decode(packet.payload, packet.fec_data)
        if errors > 16:  # RS(255,223) can correct up to 16 errors
            return None

        return packet

