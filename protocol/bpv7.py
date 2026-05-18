from __future__ import annotations

"""
BPv7 bundle helpers based on RFC 9171.

This module intentionally models the Bundle Protocol data structures without
claiming that OpenOrbitLink's compact radio packet is itself a full BPv7 wire
bundle. It gives the rest of the project a standards-shaped bundle layer for
validation, CBOR emission, CRC handling, and extension-block policy checks.
"""

import binascii
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, IntFlag
from typing import Any, Iterable, Optional


DTN_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


class BPv7ValidationError(ValueError):
    """Raised when a bundle violates an RFC 9171 structural rule."""


class CRCType(IntEnum):
    NONE = 0
    CRC16_X25 = 1
    CRC32C = 2


class BundleControlFlags(IntFlag):
    BUNDLE_IS_FRAGMENT = 0x000001
    PAYLOAD_IS_ADMINISTRATIVE_RECORD = 0x000002
    BUNDLE_MUST_NOT_BE_FRAGMENTED = 0x000004
    USER_APPLICATION_ACK_REQUESTED = 0x000020
    STATUS_TIME_REQUESTED = 0x000040
    REPORT_RECEPTION = 0x004000
    REPORT_FORWARDING = 0x010000
    REPORT_DELIVERY = 0x020000
    REPORT_DELETION = 0x040000


class BlockControlFlags(IntFlag):
    REPLICATE_IN_EVERY_FRAGMENT = 0x01
    REPORT_IF_UNPROCESSABLE = 0x02
    DELETE_BUNDLE_IF_UNPROCESSABLE = 0x04
    DISCARD_BLOCK_IF_UNPROCESSABLE = 0x10


class BlockType(IntEnum):
    PAYLOAD = 1
    PREVIOUS_NODE = 6
    BUNDLE_AGE = 7
    HOP_COUNT = 10
    BIB = 11
    BCB = 12


class URIType(IntEnum):
    DTN = 1
    IPN = 2


STATUS_REPORT_FLAGS = (
    BundleControlFlags.REPORT_RECEPTION
    | BundleControlFlags.REPORT_FORWARDING
    | BundleControlFlags.REPORT_DELIVERY
    | BundleControlFlags.REPORT_DELETION
)

PRIMARY_BLOCK_NUMBER = 0
PAYLOAD_BLOCK_NUMBER = 1


def dtn_time_ms(moment: Optional[datetime] = None) -> int:
    """Return milliseconds since the DTN epoch."""
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = moment.astimezone(timezone.utc) - DTN_EPOCH
    return int(delta.total_seconds() * 1000)


def _cbor_head(major: int, value: int) -> bytes:
    if value < 0:
        raise ValueError("CBOR helper only supports non-negative lengths/ints")
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")
    raise ValueError("CBOR uint too large")


def cbor_encode(value: Any) -> bytes:
    """
    Encode the subset of deterministic CBOR needed for BPv7 structures.

    Supported values: non-negative ints, bytes, str, bool, None, lists/tuples.
    """
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"
    if value is None:
        return b"\xf6"
    if isinstance(value, IntEnum):
        value = int(value)
    if isinstance(value, IntFlag):
        value = int(value)
    if isinstance(value, int):
        if value < 0:
            raise ValueError("BPv7 structures use CBOR unsigned integers here")
        return _cbor_head(0, value)
    if isinstance(value, bytes):
        return _cbor_head(2, len(value)) + value
    if isinstance(value, bytearray):
        data = bytes(value)
        return _cbor_head(2, len(data)) + data
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _cbor_head(3, len(data)) + data
    if isinstance(value, (list, tuple)):
        return _cbor_head(4, len(value)) + b"".join(cbor_encode(item) for item in value)
    raise TypeError(f"cannot CBOR-encode {type(value).__name__}")


def cbor_indefinite_array(encoded_items: Iterable[bytes]) -> bytes:
    """Return a CBOR indefinite-length array from already encoded items."""
    return b"\x9f" + b"".join(encoded_items) + b"\xff"


def crc16_x25(data: bytes) -> int:
    """Compute the standard X.25 CRC-16 used by BPv7 CRC type 1."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc ^ 0xFFFF


def crc32c(data: bytes) -> int:
    """Compute CRC32C (Castagnoli), used by BPv7 CRC type 2."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x82F63B78
            else:
                crc >>= 1
            crc &= 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def _zero_crc_bytes(crc_type: CRCType) -> Optional[bytes]:
    if crc_type == CRCType.NONE:
        return None
    if crc_type == CRCType.CRC16_X25:
        return b"\x00\x00"
    if crc_type == CRCType.CRC32C:
        return b"\x00\x00\x00\x00"
    raise BPv7ValidationError(f"unsupported CRC type {crc_type!r}")


def _crc_bytes(crc_type: CRCType, encoded_with_zero_crc: bytes) -> Optional[bytes]:
    if crc_type == CRCType.NONE:
        return None
    if crc_type == CRCType.CRC16_X25:
        return crc16_x25(encoded_with_zero_crc).to_bytes(2, "big")
    if crc_type == CRCType.CRC32C:
        return crc32c(encoded_with_zero_crc).to_bytes(4, "big")
    raise BPv7ValidationError(f"unsupported CRC type {crc_type!r}")


@dataclass(frozen=True)
class EndpointID:
    """A BP endpoint ID in compact BPv7 CBOR form."""

    scheme_code: int
    ssp: Any

    _DTN_RE = re.compile(r"^//[^/\s]+/[\x21-\x7e]*$")

    @classmethod
    def dtn(cls, ssp: str) -> "EndpointID":
        if ssp == "none":
            return cls(URIType.DTN, 0)
        if not cls._DTN_RE.match(ssp):
            raise ValueError("dtn SSP must be 'none' or '//node/demux'")
        return cls(URIType.DTN, ssp)

    @classmethod
    def ipn(cls, node_number: int, service_number: int) -> "EndpointID":
        if node_number < 0 or service_number < 0:
            raise ValueError("ipn node and service numbers must be unsigned")
        return cls(URIType.IPN, [node_number, service_number])

    @classmethod
    def null(cls) -> "EndpointID":
        return cls.dtn("none")

    @property
    def is_null(self) -> bool:
        return int(self.scheme_code) == URIType.DTN and self.ssp == 0

    @property
    def is_node_id_candidate(self) -> bool:
        if self.is_null:
            return False
        if int(self.scheme_code) == URIType.IPN:
            return isinstance(self.ssp, list) and len(self.ssp) == 2 and self.ssp[1] == 0
        if int(self.scheme_code) == URIType.DTN:
            return isinstance(self.ssp, str) and self.ssp.startswith("//") and self.ssp.endswith("/")
        return False

    def to_cbor_obj(self) -> list[Any]:
        return [int(self.scheme_code), self.ssp]

    def validate(self) -> None:
        if int(self.scheme_code) == URIType.DTN:
            if self.ssp == 0:
                return
            if not isinstance(self.ssp, str) or not self._DTN_RE.match(self.ssp):
                raise BPv7ValidationError("invalid dtn endpoint ID")
            return
        if int(self.scheme_code) == URIType.IPN:
            if (
                not isinstance(self.ssp, list)
                or len(self.ssp) != 2
                or not all(isinstance(item, int) and item >= 0 for item in self.ssp)
            ):
                raise BPv7ValidationError("invalid ipn endpoint ID")
            return
        raise BPv7ValidationError(f"unsupported endpoint URI scheme code {self.scheme_code!r}")


@dataclass(frozen=True)
class CreationTimestamp:
    creation_time_ms: int
    sequence_number: int

    def to_cbor_obj(self) -> list[int]:
        return [self.creation_time_ms, self.sequence_number]

    def validate(self) -> None:
        if self.creation_time_ms < 0 or self.sequence_number < 0:
            raise BPv7ValidationError("creation timestamp values must be unsigned")


@dataclass
class PrimaryBlock:
    destination: EndpointID
    source_node: EndpointID
    report_to: EndpointID
    creation_timestamp: CreationTimestamp
    lifetime_ms: int
    bundle_control_flags: int = 0
    crc_type: CRCType = CRCType.CRC16_X25
    fragment_offset: Optional[int] = None
    total_application_data_unit_length: Optional[int] = None
    crc_value: Optional[bytes] = None
    version: int = 7

    def is_fragment(self) -> bool:
        return bool(self.bundle_control_flags & BundleControlFlags.BUNDLE_IS_FRAGMENT)

    def is_administrative_record(self) -> bool:
        return bool(self.bundle_control_flags & BundleControlFlags.PAYLOAD_IS_ADMINISTRATIVE_RECORD)

    def to_cbor_obj(self, crc_override: Optional[bytes] = None) -> list[Any]:
        fields: list[Any] = [
            self.version,
            int(self.bundle_control_flags),
            int(self.crc_type),
            self.destination.to_cbor_obj(),
            self.source_node.to_cbor_obj(),
            self.report_to.to_cbor_obj(),
            self.creation_timestamp.to_cbor_obj(),
            self.lifetime_ms,
        ]
        if self.is_fragment():
            fields.extend(
                [
                    self.fragment_offset if self.fragment_offset is not None else 0,
                    (
                        self.total_application_data_unit_length
                        if self.total_application_data_unit_length is not None
                        else 0
                    ),
                ]
            )
        crc = crc_override if crc_override is not None else self.crc_value
        if self.crc_type != CRCType.NONE and crc is not None:
            fields.append(crc)
        return fields

    def encode(self, compute_crc: bool = True) -> bytes:
        crc_value = self.crc_value
        if compute_crc and self.crc_type != CRCType.NONE:
            zero_crc = _zero_crc_bytes(self.crc_type)
            encoded_zero = cbor_encode(self.to_cbor_obj(crc_override=zero_crc))
            crc_value = _crc_bytes(self.crc_type, encoded_zero)
        return cbor_encode(self.to_cbor_obj(crc_override=crc_value))

    def with_computed_crc(self) -> "PrimaryBlock":
        encoded_zero = cbor_encode(self.to_cbor_obj(crc_override=_zero_crc_bytes(self.crc_type)))
        self.crc_value = _crc_bytes(self.crc_type, encoded_zero)
        return self

    def validate(self) -> None:
        if self.version != 7:
            raise BPv7ValidationError("primary block version must be 7")
        if self.lifetime_ms < 0:
            raise BPv7ValidationError("bundle lifetime must be unsigned")
        self.destination.validate()
        self.source_node.validate()
        self.report_to.validate()
        self.creation_timestamp.validate()
        if self.crc_type not in (CRCType.NONE, CRCType.CRC16_X25, CRCType.CRC32C):
            raise BPv7ValidationError("invalid primary block CRC type")
        if self.is_fragment():
            if self.fragment_offset is None or self.total_application_data_unit_length is None:
                raise BPv7ValidationError("fragment primary block must include offset and total ADU length")
            if self.fragment_offset < 0 or self.total_application_data_unit_length < 0:
                raise BPv7ValidationError("fragment fields must be unsigned")
        else:
            if self.fragment_offset is not None or self.total_application_data_unit_length is not None:
                raise BPv7ValidationError("non-fragment primary block must not include fragment fields")
        if self.is_administrative_record() and (self.bundle_control_flags & STATUS_REPORT_FLAGS):
            raise BPv7ValidationError("administrative-record bundles must not request status reports")
        if self.source_node.is_null:
            if not (self.bundle_control_flags & BundleControlFlags.BUNDLE_MUST_NOT_BE_FRAGMENTED):
                raise BPv7ValidationError("anonymous bundles must not be fragmented")
            if self.bundle_control_flags & STATUS_REPORT_FLAGS:
                raise BPv7ValidationError("anonymous bundles must not request status reports")


@dataclass
class CanonicalBlock:
    block_type_code: int
    block_number: int
    block_control_flags: int
    crc_type: CRCType
    data: bytes
    crc_value: Optional[bytes] = None
    parsed_data: Any = field(default=None, repr=False, compare=False)

    def to_cbor_obj(self, crc_override: Optional[bytes] = None) -> list[Any]:
        fields: list[Any] = [
            self.block_type_code,
            self.block_number,
            int(self.block_control_flags),
            int(self.crc_type),
            self.data,
        ]
        crc = crc_override if crc_override is not None else self.crc_value
        if self.crc_type != CRCType.NONE and crc is not None:
            fields.append(crc)
        return fields

    def encode(self, compute_crc: bool = True) -> bytes:
        crc_value = self.crc_value
        if compute_crc and self.crc_type != CRCType.NONE:
            zero_crc = _zero_crc_bytes(self.crc_type)
            encoded_zero = cbor_encode(self.to_cbor_obj(crc_override=zero_crc))
            crc_value = _crc_bytes(self.crc_type, encoded_zero)
        return cbor_encode(self.to_cbor_obj(crc_override=crc_value))

    def with_computed_crc(self) -> "CanonicalBlock":
        encoded_zero = cbor_encode(self.to_cbor_obj(crc_override=_zero_crc_bytes(self.crc_type)))
        self.crc_value = _crc_bytes(self.crc_type, encoded_zero)
        return self

    def validate(self, primary: PrimaryBlock) -> None:
        if self.block_number <= 0:
            raise BPv7ValidationError("canonical block numbers must be positive")
        if self.block_type_code == BlockType.PAYLOAD and self.block_number != PAYLOAD_BLOCK_NUMBER:
            raise BPv7ValidationError("payload block number must be 1")
        if self.crc_type not in (CRCType.NONE, CRCType.CRC16_X25, CRCType.CRC32C):
            raise BPv7ValidationError("invalid canonical block CRC type")
        if self.crc_type == CRCType.NONE and self.crc_value is not None:
            raise BPv7ValidationError("CRC value must be omitted when CRC type is zero")
        if self.crc_type == CRCType.CRC16_X25 and self.crc_value is not None and len(self.crc_value) != 2:
            raise BPv7ValidationError("CRC-16 value must be exactly two bytes")
        if self.crc_type == CRCType.CRC32C and self.crc_value is not None and len(self.crc_value) != 4:
            raise BPv7ValidationError("CRC32C value must be exactly four bytes")
        if (
            primary.is_administrative_record() or primary.source_node.is_null
        ) and (self.block_control_flags & BlockControlFlags.REPORT_IF_UNPROCESSABLE):
            raise BPv7ValidationError(
                "admin-record and anonymous bundles must not request block-processing status reports"
            )


@dataclass(frozen=True)
class HopCount:
    hop_limit: int
    hop_count: int = 0

    def to_cbor_obj(self) -> list[int]:
        return [self.hop_limit, self.hop_count]


@dataclass
class Bundle:
    primary: PrimaryBlock
    blocks: list[CanonicalBlock]

    def payload_block(self) -> CanonicalBlock:
        if not self.blocks:
            raise BPv7ValidationError("bundle has no canonical blocks")
        payload = self.blocks[-1]
        if payload.block_type_code != BlockType.PAYLOAD:
            raise BPv7ValidationError("last canonical block must be the payload block")
        return payload

    def has_bib_targeting_primary(self) -> bool:
        for block in self.blocks:
            if block.block_type_code != BlockType.BIB:
                continue
            targets = getattr(block.parsed_data, "target_blocks", None)
            if targets and PRIMARY_BLOCK_NUMBER in targets:
                return True
        return False

    def encode(self, compute_crc: bool = True) -> bytes:
        self.validate()
        encoded = [self.primary.encode(compute_crc=compute_crc)]
        encoded.extend(block.encode(compute_crc=compute_crc) for block in self.blocks)
        return cbor_indefinite_array(encoded)

    def validate(self) -> None:
        self.primary.validate()
        if not self.blocks:
            raise BPv7ValidationError("bundle must include at least one canonical block")
        self.payload_block()
        payload_count = sum(1 for block in self.blocks if block.block_type_code == BlockType.PAYLOAD)
        if payload_count != 1:
            raise BPv7ValidationError("bundle must contain exactly one payload block")
        numbers = [block.block_number for block in self.blocks]
        if len(numbers) != len(set(numbers)):
            raise BPv7ValidationError("canonical block numbers must be unique")
        for block in self.blocks:
            block.validate(self.primary)
        if self.primary.crc_type == CRCType.NONE and not self.has_bib_targeting_primary():
            raise BPv7ValidationError("primary block CRC may be zero only when a BIB targets the primary block")
        previous_node_count = sum(1 for block in self.blocks if block.block_type_code == BlockType.PREVIOUS_NODE)
        if previous_node_count > 1:
            raise BPv7ValidationError("bundle must not contain multiple Previous Node blocks")
        age_blocks = [block for block in self.blocks if block.block_type_code == BlockType.BUNDLE_AGE]
        if self.primary.creation_timestamp.creation_time_ms == 0 and len(age_blocks) != 1:
            raise BPv7ValidationError("bundles with unknown creation time must contain exactly one Bundle Age block")
        if self.primary.creation_timestamp.creation_time_ms != 0 and len(age_blocks) > 1:
            raise BPv7ValidationError("bundle must not contain multiple Bundle Age blocks")
        hop_blocks = [block for block in self.blocks if block.block_type_code == BlockType.HOP_COUNT]
        if len(hop_blocks) > 1:
            raise BPv7ValidationError("bundle must not contain multiple Hop Count blocks")
        if hop_blocks:
            hop = hop_blocks[0].parsed_data
            if isinstance(hop, HopCount) and not (1 <= hop.hop_limit <= 255):
                raise BPv7ValidationError("Hop Count hop limit must be in the range 1..255")


def payload_block(payload: bytes, crc_type: CRCType = CRCType.CRC16_X25) -> CanonicalBlock:
    return CanonicalBlock(
        block_type_code=BlockType.PAYLOAD,
        block_number=PAYLOAD_BLOCK_NUMBER,
        block_control_flags=0,
        crc_type=crc_type,
        data=payload,
    )


def previous_node_block(node_id: EndpointID, block_number: int = 2) -> CanonicalBlock:
    node_id.validate()
    return CanonicalBlock(
        block_type_code=BlockType.PREVIOUS_NODE,
        block_number=block_number,
        block_control_flags=0,
        crc_type=CRCType.CRC16_X25,
        data=cbor_encode(node_id.to_cbor_obj()),
        parsed_data=node_id,
    )


def bundle_age_block(age_ms: int, block_number: int = 2) -> CanonicalBlock:
    if age_ms < 0:
        raise ValueError("bundle age must be unsigned")
    return CanonicalBlock(
        block_type_code=BlockType.BUNDLE_AGE,
        block_number=block_number,
        block_control_flags=0,
        crc_type=CRCType.CRC16_X25,
        data=cbor_encode(age_ms),
        parsed_data=age_ms,
    )


def hop_count_block(hop_limit: int, hop_count: int = 0, block_number: int = 2) -> CanonicalBlock:
    hop = HopCount(hop_limit=hop_limit, hop_count=hop_count)
    return CanonicalBlock(
        block_type_code=BlockType.HOP_COUNT,
        block_number=block_number,
        block_control_flags=0,
        crc_type=CRCType.CRC16_X25,
        data=cbor_encode(hop.to_cbor_obj()),
        parsed_data=hop,
    )


def bundle_identity(bundle: Bundle) -> str:
    """Return a stable, readable identity string for bundle tracking."""
    source = cbor_encode(bundle.primary.source_node.to_cbor_obj())
    created = bundle.primary.creation_timestamp.creation_time_ms
    seq = bundle.primary.creation_timestamp.sequence_number
    fragment = ""
    if bundle.primary.is_fragment():
        fragment = (
            f":{bundle.primary.fragment_offset}:"
            f"{bundle.primary.total_application_data_unit_length}"
        )
    digest = binascii.hexlify(source).decode("ascii")
    return f"bpv7:{digest}:{created}:{seq}{fragment}"
