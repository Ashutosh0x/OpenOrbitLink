"""
OpenOrbitLink BPv7 -- Bundle Protocol Version 7 (RFC 9171) Implementation

CBOR-encoded bundle serialization with BPSec (RFC 9172) integrity and
confidentiality blocks. Designed for store-and-forward DTN messaging
over satellite and LoRa links.

Key structures:
  - PrimaryBlock: Source/destination EIDs, creation timestamp, lifetime
  - PayloadBlock: Carries the OpenOrbitLink packet bytes
  - BIB: Block Integrity Block (HMAC-SHA256) -- allowed on all bands
  - BCB: Block Confidentiality Block (AES-256-GCM) -- ISM/NTN only

Wire format uses CBOR (RFC 8949) for compact encoding, suitable for
the 80-byte LoRa frame constraint.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

try:
    import cbor2
    HAS_CBOR = True
except ImportError:
    HAS_CBOR = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class BlockType(IntEnum):
    """BPv7 block type codes (RFC 9171 Section 4.3.2)."""
    PRIMARY = 0
    PAYLOAD = 1
    PREVIOUS_NODE = 6
    BUNDLE_AGE = 7
    HOP_COUNT = 10
    BIB = 11
    BCB = 12


class CRCType(IntEnum):
    NONE = 0
    CRC16 = 1
    CRC16_X25 = 1     # Alias used by bpsec.py
    CRC32 = 2


# Backwards-compat constants used by security/bpsec.py
PRIMARY_BLOCK_NUMBER = 0
PAYLOAD_BLOCK_NUMBER = 1


class BPv7ValidationError(ValueError):
    """Raised when a BPv7 bundle fails validation."""


class BlockControlFlags(IntEnum):
    """Block processing control flags (RFC 9171 Section 4.3.4)."""
    NONE = 0x00
    REPLICATE_IN_EVERY_FRAGMENT = 0x01
    TRANSMIT_STATUS_IF_UNPROCESSABLE = 0x02
    DELETE_BUNDLE_IF_UNPROCESSABLE = 0x04
    DISCARD_BLOCK_IF_UNPROCESSABLE = 0x10
    # Bundle processing control flags (used in PrimaryBlock)
    BUNDLE_MUST_NOT_BE_FRAGMENTED = 0x04
    REPORT_RECEPTION = 0x4000
    REPORT_FORWARDING = 0x10000
    REPORT_DELIVERY = 0x20000
    REPORT_DELETION = 0x40000


def cbor_encode(obj) -> bytes:
    """Encode a Python object to CBOR bytes."""
    if HAS_CBOR:
        return cbor2.dumps(obj)
    # Minimal fallback: json-encoded bytes
    import json
    return json.dumps(obj).encode("utf-8")


# Aliases for protocol/__init__.py backwards compat
BundleControlFlags = BlockControlFlags

from collections import namedtuple
CreationTimestamp = namedtuple('CreationTimestamp', ['time_ms', 'sequence'])


def payload_block(first=None, data: bytes = None, **kwargs) -> 'CanonicalBlock':
    """Create a payload canonical block.

    Accepts both:
        payload_block(b"data")           -- data only, block_number=1
        payload_block(2, b"data")        -- explicit block_number
    """
    if isinstance(first, bytes):
        # payload_block(b"data")
        return CanonicalBlock(
            block_type=BlockType.PAYLOAD,
            block_number=1,
            data=first,
            **kwargs,
        )
    elif isinstance(first, int) and data is not None:
        # payload_block(2, b"data")
        return CanonicalBlock(
            block_type=BlockType.PAYLOAD,
            block_number=first,
            data=data,
            **kwargs,
        )
    else:
        # Fallback
        return CanonicalBlock(
            block_type=BlockType.PAYLOAD,
            block_number=first or 1,
            data=data or b"",
            **kwargs,
        )


def crc16_x25(data: bytes) -> int:
    """CRC-16/X-25 (used by AX.25 FCS). Poly=0x1021, init=0xFFFF, refin/out, xorout=0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc ^ 0xFFFF



class BundleFlags(IntEnum):
    NONE = 0x00
    IS_FRAGMENT = 0x01
    ADM_RECORD = 0x02
    NO_FRAGMENT = 0x04
    ACK_REQUESTED = 0x20
    STATUS_TIME = 0x40


@dataclass
class EndpointID:
    """BPv7 Endpoint Identifier using dtn scheme."""
    scheme: int = 1
    specific_part: str = ""

    @classmethod
    def from_device_id(cls, device_id: str, service: str = "inbox") -> 'EndpointID':
        return cls(scheme=1, specific_part=f"//ool-{device_id}/{service}")

    @classmethod
    def null(cls) -> 'EndpointID':
        return cls(scheme=1, specific_part="//none")

    @classmethod
    def ipn(cls, node: int, service: int = 0) -> 'EndpointID':
        """Create an IPN-scheme endpoint ID."""
        return cls(scheme=2, specific_part=f"{node}.{service}")

    def to_cbor(self) -> list:
        return [self.scheme, self.specific_part]

    @classmethod
    def from_cbor(cls, data: list) -> 'EndpointID':
        return cls(scheme=data[0], specific_part=data[1])

    def __str__(self) -> str:
        return f"dtn:{self.specific_part}"

    def to_cbor_obj(self) -> list:
        """Alias for bpsec compat."""
        return self.to_cbor()

    def validate(self) -> None:
        """Validate the endpoint ID."""
        if self.scheme not in (1, 2):
            raise BPv7ValidationError(f"unknown EID scheme: {self.scheme}")


@dataclass
class PrimaryBlock:
    """BPv7 Primary Block (RFC 9171 Section 4.3.1)."""
    version: int = 7
    flags: int = BundleFlags.NONE
    crc_type: CRCType = CRCType.CRC16
    destination: EndpointID = field(default_factory=EndpointID.null)
    source: EndpointID = field(default_factory=EndpointID.null)
    report_to: EndpointID = field(default_factory=EndpointID.null)
    creation_timestamp: tuple = (0, 0)
    lifetime_ms: int = 86_400_000
    # Compat fields for old-style constructor
    source_node: Optional[EndpointID] = None
    bundle_control_flags: Optional[int] = None

    def __post_init__(self):
        # Compat: source_node -> source
        if self.source_node is not None:
            self.source = self.source_node
            self.source_node = None
        # Compat: bundle_control_flags -> flags
        if self.bundle_control_flags is not None:
            self.flags = self.bundle_control_flags
            self.bundle_control_flags = None

    def to_cbor(self) -> list:
        ts = self.creation_timestamp
        if ts == (0, 0):
            ts = (int(time.time() * 1000), 0)
        return [
            self.version, self.flags, self.crc_type,
            self.destination.to_cbor(), self.source.to_cbor(),
            self.report_to.to_cbor(), list(ts), self.lifetime_ms,
        ]

    def encode(self) -> bytes:
        """Encode primary block to CBOR bytes."""
        return cbor_encode(self.to_cbor())

    @classmethod
    def from_cbor(cls, data: list) -> 'PrimaryBlock':
        return cls(
            version=data[0], flags=data[1], crc_type=CRCType(data[2]),
            destination=EndpointID.from_cbor(data[3]),
            source=EndpointID.from_cbor(data[4]),
            report_to=EndpointID.from_cbor(data[5]),
            creation_timestamp=tuple(data[6]), lifetime_ms=data[7],
        )

    def is_fragment(self) -> bool:
        """Check if this bundle is a fragment."""
        return bool(self.flags & BundleFlags.IS_FRAGMENT)


@dataclass
class CanonicalBlock:
    """BPv7 Canonical Block (RFC 9171 Section 4.3.2)."""
    block_type: BlockType = BlockType.PAYLOAD
    block_number: int = 0
    flags: int = 0
    crc_type: CRCType = CRCType.NONE
    data: bytes = b""
    # Compat fields for bpsec.py
    block_type_code: Optional[int] = None
    block_control_flags: int = 0
    parsed_data: object = None

    def __post_init__(self):
        # Sync compat fields
        if self.block_type_code is None:
            self.block_type_code = int(self.block_type)
        else:
            self.block_type = BlockType(self.block_type_code)
        if self.block_control_flags:
            self.flags = self.block_control_flags
        else:
            self.block_control_flags = self.flags

    def to_cbor(self) -> list:
        return [self.block_type, self.block_number, self.flags, self.crc_type, self.data]

    @classmethod
    def from_cbor(cls, data: list) -> 'CanonicalBlock':
        return cls(
            block_type=BlockType(data[0]), block_number=data[1],
            flags=data[2], crc_type=CRCType(data[3]), data=data[4],
        )


class BPv7Bundle:
    """A complete BPv7 bundle with BPSec support.

    Supports both old-style constructor:
        BPv7Bundle(primary_block, [canonical_blocks])
    And new-style:
        BPv7Bundle(primary=..., payload=..., extension_blocks=[...])
    """

    def __init__(self, primary=None, blocks=None, *, payload=b"", extension_blocks=None, bundle_id=""):
        if primary is None:
            primary = PrimaryBlock()
        self.primary = primary

        if blocks is not None:
            # Old-style: BPv7Bundle(primary, [block1, block2, ...])
            self.extension_blocks = []
            self.payload = payload
            for block in blocks:
                if block.block_type == BlockType.PAYLOAD:
                    self.payload = block.data
                else:
                    self.extension_blocks.append(block)
        else:
            self.payload = payload
            self.extension_blocks = extension_blocks if extension_blocks is not None else []

        if bundle_id:
            self.bundle_id = bundle_id
        else:
            src = str(self.primary.source)
            ts = self.primary.creation_timestamp
            self.bundle_id = f"{src}-{ts[0]}-{ts[1]}"

    def serialize(self) -> bytes:
        """Serialize bundle to CBOR bytes (indefinite-length array per RFC 9171)."""
        if not HAS_CBOR:
            return self._serialize_compact()
        # RFC 9171 Section 4.1: bundles are serialized as CBOR indefinite-length arrays
        parts = bytearray(b'\x9f')  # CBOR indefinite-length array start
        parts.extend(cbor2.dumps(self.primary.to_cbor()))
        pb = CanonicalBlock(
            block_type=BlockType.PAYLOAD, block_number=1, data=self.payload,
        )
        parts.extend(cbor2.dumps(pb.to_cbor()))
        for block in self.extension_blocks:
            parts.extend(cbor2.dumps(block.to_cbor()))
        parts.extend(b'\xff')  # CBOR break code
        return bytes(parts)

    def encode(self) -> bytes:
        """Alias for serialize() -- backwards compat."""
        return self.serialize()


    @classmethod
    def deserialize(cls, data: bytes) -> Optional['BPv7Bundle']:
        """Deserialize bundle from CBOR bytes."""
        if not HAS_CBOR:
            return cls._deserialize_compact(data)
        try:
            blocks = cbor2.loads(data)
            if not blocks or not isinstance(blocks, list):
                return None
            primary = PrimaryBlock.from_cbor(blocks[0])
            payload = b""
            extensions = []
            for block_data in blocks[1:]:
                block = CanonicalBlock.from_cbor(block_data)
                if block.block_type == BlockType.PAYLOAD:
                    payload = block.data
                else:
                    extensions.append(block)
            return cls(primary=primary, payload=payload, extension_blocks=extensions)
        except Exception:
            return None

    def _serialize_compact(self) -> bytes:
        """Compact binary serialization when CBOR is not available."""
        src_bytes = str(self.primary.source).encode("utf-8")[:32]
        dst_bytes = str(self.primary.destination).encode("utf-8")[:32]
        ts = int(time.time())
        header = struct.pack(">BHBB", 7, self.primary.flags, len(src_bytes), len(dst_bytes))
        ts_bytes = struct.pack(">I", ts)
        lifetime = struct.pack(">I", self.primary.lifetime_ms)
        payload_len = struct.pack(">H", len(self.payload))
        return header + ts_bytes + lifetime + src_bytes + dst_bytes + payload_len + self.payload

    @classmethod
    def _deserialize_compact(cls, data: bytes) -> Optional['BPv7Bundle']:
        """Compact binary deserialization fallback."""
        if len(data) < 14:
            return None
        try:
            version, flags, src_len, dst_len = struct.unpack(">BHBB", data[:5])
            ts = struct.unpack(">I", data[5:9])[0]
            lifetime = struct.unpack(">I", data[9:13])[0]
            offset = 13
            src = data[offset:offset + src_len].decode("utf-8")
            offset += src_len
            dst = data[offset:offset + dst_len].decode("utf-8")
            offset += dst_len
            if offset + 2 > len(data):
                return None
            payload_len = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += 2
            payload = data[offset:offset + payload_len]
            bundle = cls()
            bundle.primary.version = version
            bundle.primary.flags = flags
            bundle.primary.source = EndpointID(specific_part=src)
            bundle.primary.destination = EndpointID(specific_part=dst)
            bundle.primary.creation_timestamp = (ts * 1000, 0)
            bundle.primary.lifetime_ms = lifetime
            bundle.payload = payload
            return bundle
        except Exception:
            return None

    def add_integrity(self, key: bytes) -> None:
        """Add BIB (HMAC-SHA256). Allowed on ALL bands including amateur."""
        mac = hmac.new(key, self.payload, hashlib.sha256).digest()
        bib = CanonicalBlock(
            block_type=BlockType.BIB,
            block_number=len(self.extension_blocks) + 2,
            data=mac,
        )
        self.extension_blocks.append(bib)

    def verify_integrity(self, key: bytes) -> bool:
        """Verify the BIB if present."""
        for block in self.extension_blocks:
            if block.block_type == BlockType.BIB:
                expected = hmac.new(key, self.payload, hashlib.sha256).digest()
                return hmac.compare_digest(block.data, expected)
        return True

    def add_confidentiality(self, key: bytes, band: str = "ism") -> None:
        """Add BCB (AES-256-GCM). BLOCKED on amateur bands."""
        if band.lower() == "amateur":
            raise ValueError(
                "BCB confidentiality blocks are prohibited on amateur bands. "
                "Use BIB integrity blocks only."
            )
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography package required for BCB")
        nonce = os.urandom(12)
        aesgcm = AESGCM(key[:32])
        ciphertext = aesgcm.encrypt(nonce, self.payload, None)
        self.payload = ciphertext
        bcb = CanonicalBlock(
            block_type=BlockType.BCB,
            block_number=len(self.extension_blocks) + 2,
            data=nonce,
        )
        self.extension_blocks.append(bcb)

    def decrypt_confidentiality(self, key: bytes) -> bool:
        """Decrypt BCB-protected payload if present."""
        if not HAS_CRYPTO:
            return False
        for block in self.extension_blocks:
            if block.block_type == BlockType.BCB:
                nonce = block.data
                aesgcm = AESGCM(key[:32])
                try:
                    plaintext = aesgcm.decrypt(nonce, self.payload, None)
                    self.payload = plaintext
                    return True
                except Exception:
                    return False
        return True

    # --- bpsec.py compatibility ---

    @property
    def blocks(self) -> list[CanonicalBlock]:
        """All canonical blocks (payload + extensions) for bpsec.py compat."""
        payload_block = CanonicalBlock(
            block_type=BlockType.PAYLOAD,
            block_number=PAYLOAD_BLOCK_NUMBER,
            data=self.payload,
        )
        return [payload_block] + self.extension_blocks

    def validate(self) -> None:
        """Validate bundle structure per RFC 9171."""
        if self.primary.version != 7:
            raise BPv7ValidationError(f"unsupported BPv7 version: {self.primary.version}")
        # RFC 9171 Section 4.2.3: anonymous bundles must not request status reports
        report_flags = (
            BlockControlFlags.REPORT_RECEPTION
            | BlockControlFlags.REPORT_FORWARDING
            | BlockControlFlags.REPORT_DELIVERY
            | BlockControlFlags.REPORT_DELETION
        )
        is_anonymous = (
            self.primary.source.specific_part in ("//none", "")
            or str(self.primary.source) == "dtn://none"
        )
        if is_anonymous and (self.primary.flags & report_flags):
            raise BPv7ValidationError(
                "anonymous bundles must not request status reports (RFC 9171 Section 4.2.3)"
            )

    def get_payload_block(self) -> CanonicalBlock:
        """Return the payload canonical block."""
        return CanonicalBlock(
            block_type=BlockType.PAYLOAD,
            block_number=PAYLOAD_BLOCK_NUMBER,
            data=self.payload,
        )

    # Alias for old test compat
    payload_block = get_payload_block


# Backwards-compat alias used by security/bpsec.py
Bundle = BPv7Bundle

