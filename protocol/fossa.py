from __future__ import annotations

"""
FOSSA/TinyGS LoRa transport framing for OpenOrbitLink payloads.

FOSSA's public FAQ describes LoRa payloads around 80 bytes at low data rates,
so this frame keeps the satellite uplink unit intentionally small. It is an
OpenOrbitLink application frame carried over a FOSSA-compatible LoRa path, not
a proprietary FOSSA network protocol.
"""

import base64
from dataclasses import dataclass
from enum import IntEnum

from .packet import PayloadType, crc16_ccitt


FOSSA_MAX_FRAME_BYTES = 80
FOSSA_MAGIC = b"OOL"
FOSSA_VERSION = 1
FOSSA_HEADER_BYTES = 9
FOSSA_CRC_BYTES = 2
FOSSA_MAX_PAYLOAD_BYTES = FOSSA_MAX_FRAME_BYTES - FOSSA_HEADER_BYTES - FOSSA_CRC_BYTES


class FossaFrameError(ValueError):
    """Raised when a FOSSA transport frame is malformed."""


class FossaFrameFlags(IntEnum):
    NONE = 0
    ENCRYPTED = 1
    ACK_REQUESTED = 2
    FRAGMENT = 4


@dataclass(frozen=True)
class FossaFrame:
    payload_type: PayloadType
    sequence: int
    payload: bytes
    flags: int = int(FossaFrameFlags.NONE)
    ttl: int = 4

    def encode(self) -> bytes:
        if not 0 <= self.sequence <= 0xFFFF:
            raise FossaFrameError("sequence must fit in 16 bits")
        if not 0 <= self.flags <= 0xFF:
            raise FossaFrameError("flags must fit in 8 bits")
        if not 0 <= self.ttl <= 0xFF:
            raise FossaFrameError("ttl must fit in 8 bits")
        if len(self.payload) > FOSSA_MAX_PAYLOAD_BYTES:
            raise FossaFrameError(
                f"payload exceeds {FOSSA_MAX_PAYLOAD_BYTES} bytes for an {FOSSA_MAX_FRAME_BYTES}-byte FOSSA frame"
            )
        header = (
            FOSSA_MAGIC
            + bytes([FOSSA_VERSION, int(self.payload_type)])
            + self.sequence.to_bytes(2, "big")
            + bytes([self.flags, self.ttl])
        )
        body = header + self.payload
        crc = crc16_ccitt(body).to_bytes(2, "big")
        return body + crc

    def to_base64(self) -> str:
        return base64.b64encode(self.encode()).decode("ascii")

    @classmethod
    def decode(cls, raw: bytes) -> "FossaFrame":
        if len(raw) < FOSSA_HEADER_BYTES + FOSSA_CRC_BYTES:
            raise FossaFrameError("frame too short")
        if len(raw) > FOSSA_MAX_FRAME_BYTES:
            raise FossaFrameError("frame exceeds FOSSA LoRa payload limit")
        if raw[:3] != FOSSA_MAGIC:
            raise FossaFrameError("invalid FOSSA frame magic")
        if raw[3] != FOSSA_VERSION:
            raise FossaFrameError(f"unsupported FOSSA frame version {raw[3]}")
        expected_crc = int.from_bytes(raw[-2:], "big")
        actual_crc = crc16_ccitt(raw[:-2])
        if expected_crc != actual_crc:
            raise FossaFrameError("FOSSA frame CRC failed")
        try:
            payload_type = PayloadType(raw[4])
        except ValueError as exc:
            raise FossaFrameError("unknown payload type") from exc
        return cls(
            payload_type=payload_type,
            sequence=int.from_bytes(raw[5:7], "big"),
            flags=raw[7],
            ttl=raw[8],
            payload=raw[9:-2],
        )

    @classmethod
    def from_base64(cls, encoded: str) -> "FossaFrame":
        return cls.decode(base64.b64decode(encoded.encode("ascii"), validate=True))


def packet_payload_to_fossa_frames(
    payload_type: PayloadType,
    payload: bytes,
    start_sequence: int = 0,
    encrypted: bool = False,
) -> list[FossaFrame]:
    """Fragment an OpenOrbitLink payload into small FOSSA transport frames."""
    frames: list[FossaFrame] = []
    flags = int(FossaFrameFlags.ENCRYPTED) if encrypted else int(FossaFrameFlags.NONE)
    for offset in range(0, len(payload), FOSSA_MAX_PAYLOAD_BYTES):
        chunk = payload[offset:offset + FOSSA_MAX_PAYLOAD_BYTES]
        frame_flags = flags
        if len(payload) > FOSSA_MAX_PAYLOAD_BYTES:
            frame_flags |= int(FossaFrameFlags.FRAGMENT)
        frames.append(
            FossaFrame(
                payload_type=payload_type,
                sequence=(start_sequence + len(frames)) & 0xFFFF,
                payload=chunk,
                flags=frame_flags,
            )
        )
    if not frames:
        frames.append(FossaFrame(payload_type=payload_type, sequence=start_sequence & 0xFFFF, payload=b"", flags=flags))
    return frames
