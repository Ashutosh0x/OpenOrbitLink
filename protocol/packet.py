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

from security import BandType, encryption_policy_for_band


# ─── Packet Constants ────────────────────────────────────────────────────────

SYNC_WORD = b'\xFE\x6B\x28\x40'     # 4-byte sync + Barker-13 prefix
PROTOCOL_VERSION = 1
MAX_PAYLOAD_SIZE = 2048               # bytes
CRC16_POLY = 0x1021                   # CRC-16 CCITT polynomial
PACKET_FLAG_ENCRYPTED = 0x01
HEADER_FORMAT = '>4s6sIBBBBBH'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class PayloadType(IntEnum):
    TEXT = 0x01
    VOICE = 0x02
    SOS = 0x03
    RELAY = 0x04
    ACK = 0x05
    BEACON = 0x06


class TransmitBand(IntEnum):
    UNKNOWN = 0
    AMATEUR = 1
    ISM = 2
    LICENSED = 3
    CARRIER_NTN = 4
    NTN = 4  # Backward-compatible alias for packets serialized before the explicit carrier name.
    RECEIVE_ONLY = 5

    @classmethod
    def from_value(cls, value: "TransmitBand | BandType | str | int") -> "TransmitBand":
        if isinstance(value, cls):
            return value
        if isinstance(value, BandType):
            return _SECURITY_TO_TRANSMIT_BAND[value]
        if isinstance(value, int):
            return cls(value)
        return _SECURITY_TO_TRANSMIT_BAND[BandType.from_value(value)]

    @property
    def security_band(self) -> BandType:
        return _TRANSMIT_TO_SECURITY_BAND[self]


_TRANSMIT_TO_SECURITY_BAND: dict[TransmitBand, BandType] = {
    TransmitBand.UNKNOWN: BandType.UNKNOWN,
    TransmitBand.AMATEUR: BandType.AMATEUR,
    TransmitBand.ISM: BandType.ISM,
    TransmitBand.LICENSED: BandType.LICENSED,
    TransmitBand.CARRIER_NTN: BandType.NTN,
    TransmitBand.RECEIVE_ONLY: BandType.RECEIVE_ONLY,
}
_SECURITY_TO_TRANSMIT_BAND = {value: key for key, value in _TRANSMIT_TO_SECURITY_BAND.items()}


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
    payload: bytes                # variable payload
    transmit_band: TransmitBand = TransmitBand.UNKNOWN
    is_encrypted: bool = False
    fec_data: bytes = b''         # 32 bytes — Reed-Solomon parity
    sequence_num: int = 0         # For ordering
    hop_count: int = 0            # Number of relay hops
    ttl: int = 10                 # Maximum hops

    @property
    def hop_limit_exceeded(self) -> bool:
        """True when the packet must no longer be relayed."""
        return self.hop_count >= self.ttl

    def relay_copy(self) -> 'OpenOrbitLinkPacket':
        """Return a copy prepared for the next relay hop."""
        if self.hop_limit_exceeded:
            raise ValueError("packet hop limit exceeded")
        return OpenOrbitLinkPacket(
            device_id=self.device_id,
            timestamp=self.timestamp,
            payload_type=self.payload_type,
            payload=self.payload,
            transmit_band=self.transmit_band,
            is_encrypted=self.is_encrypted,
            fec_data=self.fec_data,
            sequence_num=self.sequence_num,
            hop_count=self.hop_count + 1,
            ttl=self.ttl,
        )

    def serialize(self) -> bytes:
        """Serialize packet to wire format bytes."""
        if len(self.device_id) != 6:
            raise ValueError("device_id must be exactly 6 bytes")
        if len(self.payload) > MAX_PAYLOAD_SIZE:
            raise ValueError(f"payload exceeds {MAX_PAYLOAD_SIZE} bytes")
        if not (0 <= self.hop_count <= 255 and 0 <= self.ttl <= 255):
            raise ValueError("hop_count and ttl must fit in one byte")
        if not isinstance(self.transmit_band, TransmitBand):
            self.transmit_band = TransmitBand.from_value(self.transmit_band)
        self.assert_encryption_policy()

        flags = PACKET_FLAG_ENCRYPTED if self.is_encrypted else 0
        header = struct.pack(
            HEADER_FORMAT,
            SYNC_WORD,
            self.device_id,
            self.timestamp & 0xFFFFFFFF,
            self.payload_type,
            self.transmit_band,
            flags,
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
        if len(data) < HEADER_SIZE + 32 + 2:  # header + FEC + CRC
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
        try:
            payload_type = PayloadType(data[14])
            transmit_band = TransmitBand(data[15])
        except ValueError:
            return None
        flags = data[16]
        if flags & ~PACKET_FLAG_ENCRYPTED:
            return None
        hop_count = data[17]
        ttl = data[18]
        payload_len = struct.unpack('>H', data[19:21])[0]
        if payload_len > MAX_PAYLOAD_SIZE:
            return None

        expected_len = HEADER_SIZE + payload_len + 32 + 2
        if len(data) != expected_len:
            return None

        # Extract payload and FEC
        payload = data[HEADER_SIZE:HEADER_SIZE + payload_len]
        fec_start = HEADER_SIZE + payload_len
        fec_data = data[fec_start:fec_start + 32]

        return cls(
            device_id=device_id,
            timestamp=timestamp,
            payload_type=payload_type,
            payload=payload,
            transmit_band=transmit_band,
            is_encrypted=bool(flags & PACKET_FLAG_ENCRYPTED),
            fec_data=fec_data,
            hop_count=hop_count,
            ttl=ttl,
        )

    def assert_encryption_policy(self) -> None:
        """Ensure encrypted payloads are not serialized for prohibited bands."""
        policy = encryption_policy_for_band(self.transmit_band.security_band)
        if self.is_encrypted:
            policy.assert_encryption_allowed()
        else:
            policy.assert_plaintext_allowed()

    def overhead_stats(self) -> dict[str, float | int]:
        """Return packet overhead accounting before RF modulation/FEC interleaving."""
        payload_bytes = len(self.payload)
        fec_bytes = 32
        crc_bytes = 2
        total_bytes = HEADER_SIZE + payload_bytes + fec_bytes + crc_bytes
        overhead_bytes = total_bytes - payload_bytes
        return {
            "header_bytes": HEADER_SIZE,
            "payload_bytes": payload_bytes,
            "fec_bytes": fec_bytes,
            "crc_bytes": crc_bytes,
            "total_bytes": total_bytes,
            "overhead_bytes": overhead_bytes,
            "overhead_percent": 0.0 if total_bytes == 0 else 100.0 * overhead_bytes / total_bytes,
        }

    def transmit_time_seconds(self, bitrate_bps: float) -> float:
        """Return on-air time estimate at the given raw bitrate."""
        if bitrate_bps <= 0:
            raise ValueError("bitrate_bps must be positive")
        return (self.overhead_stats()["total_bytes"] * 8) / bitrate_bps

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

    Note: the current Python prototype stores a fixed 32-byte parity field per
    OpenOrbitLink packet. A production RS(255,223) implementation must account
    for block interleaving and the full 32 parity bytes per 223 data bytes.
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

    def create_text_message(
        self,
        text: str,
        encrypt: bool = False,
        band: TransmitBand | BandType | str = TransmitBand.ISM,
    ) -> OpenOrbitLinkPacket:
        """Create a text message packet."""
        payload = text.encode('utf-8')[:256]
        return self._build_packet(PayloadType.TEXT, payload, band=band, is_encrypted=encrypt)

    def create_voice_packet(
        self,
        codec2_frames: bytes,
        band: TransmitBand | BandType | str = TransmitBand.ISM,
        encrypt: bool = False,
    ) -> OpenOrbitLinkPacket:
        """Create a voice packet from Codec2 encoded frames."""
        return self._build_packet(PayloadType.VOICE, codec2_frames[:1024], band=band, is_encrypted=encrypt)

    def create_sos(
        self,
        lat: float,
        lon: float,
        message: str = "",
        band: TransmitBand | BandType | str = TransmitBand.ISM,
    ) -> OpenOrbitLinkPacket:
        """Create emergency SOS packet with GPS coordinates."""
        payload = struct.pack('>ff', lat, lon) + message.encode('utf-8')[:56]
        return self._build_packet(PayloadType.SOS, payload, band=band, is_encrypted=False)

    def create_beacon(
        self,
        capabilities: int = 0xFF,
        band: TransmitBand | BandType | str = TransmitBand.ISM,
    ) -> OpenOrbitLinkPacket:
        """Create network presence beacon."""
        payload = struct.pack('>BH', capabilities, self._seq_counter)
        return self._build_packet(PayloadType.BEACON, payload, band=band, is_encrypted=False)

    def create_ack(
        self,
        original_device_id: bytes,
        original_seq: int,
        band: TransmitBand | BandType | str = TransmitBand.ISM,
    ) -> OpenOrbitLinkPacket:
        """Create delivery acknowledgment."""
        payload = original_device_id[:6] + struct.pack('>I', original_seq)
        return self._build_packet(PayloadType.ACK, payload, band=band, is_encrypted=False)

    def create_encrypted_packet(
        self,
        ptype: PayloadType,
        ciphertext: bytes,
        band: TransmitBand | BandType | str,
    ) -> OpenOrbitLinkPacket:
        """Build a packet around ciphertext produced by the security layer."""
        return self._build_packet(ptype, ciphertext, band=band, is_encrypted=True)

    def _build_packet(
        self,
        ptype: PayloadType,
        payload: bytes,
        band: TransmitBand | BandType | str = TransmitBand.ISM,
        is_encrypted: bool = False,
    ) -> OpenOrbitLinkPacket:
        """Build a complete packet with FEC."""
        self._seq_counter += 1
        fec_data = self.fec.encode(payload)
        transmit_band = TransmitBand.from_value(band)

        packet = OpenOrbitLinkPacket(
            device_id=self.device_id,
            timestamp=int(time.time()),
            payload_type=ptype,
            payload=payload,
            transmit_band=transmit_band,
            is_encrypted=is_encrypted,
            fec_data=fec_data,
            sequence_num=self._seq_counter,
        )
        packet.assert_encryption_policy()
        return packet

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
