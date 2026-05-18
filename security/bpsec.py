from __future__ import annotations

"""
BPSec block helpers based on RFC 9172.

The code here models BIB and BCB metadata and validates security-block
relationships. Cryptographic suites remain pluggable; this module enforces
the protocol invariants that must be true before a bundle is processed or
forwarded.
"""

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any

from . import BandType, encryption_policy_for_band
from protocol.bpv7 import (
    BPv7ValidationError,
    BlockControlFlags,
    BlockType,
    Bundle,
    CanonicalBlock,
    CRCType,
    EndpointID,
    PRIMARY_BLOCK_NUMBER,
    PAYLOAD_BLOCK_NUMBER,
    cbor_encode,
)


class BPSecValidationError(BPv7ValidationError):
    """Raised when BPSec block relationships violate RFC 9172."""


class SecurityContextFlags(IntFlag):
    PARAMETERS_PRESENT = 0x01


class SecurityReasonCode(IntEnum):
    MISSING_SECURITY_OPERATION = 12
    UNKNOWN_SECURITY_OPERATION = 13
    UNEXPECTED_SECURITY_OPERATION = 14
    FAILED_SECURITY_OPERATION = 15
    CONFLICTING_SECURITY_OPERATION = 16


@dataclass(frozen=True)
class SecurityParameter:
    parameter_id: int
    value: Any

    def to_cbor_obj(self) -> list[Any]:
        return [self.parameter_id, self.value]


@dataclass(frozen=True)
class SecurityResult:
    result_id: int
    value: Any

    def to_cbor_obj(self) -> list[Any]:
        return [self.result_id, self.value]


@dataclass
class AbstractSecurityBlock:
    target_blocks: list[int]
    security_context_id: int
    security_source: EndpointID
    security_context_flags: int = 0
    security_context_parameters: list[SecurityParameter] = field(default_factory=list)
    security_results: list[list[SecurityResult]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.security_context_parameters:
            self.security_context_flags |= SecurityContextFlags.PARAMETERS_PRESENT
        if not self.security_results:
            self.security_results = [[] for _ in self.target_blocks]

    def to_cbor_obj(self) -> list[Any]:
        fields: list[Any] = [
            self.target_blocks,
            self.security_context_id,
            int(self.security_context_flags),
            self.security_source.to_cbor_obj(),
        ]
        if self.security_context_flags & SecurityContextFlags.PARAMETERS_PRESENT:
            fields.append([param.to_cbor_obj() for param in self.security_context_parameters])
        fields.append([[result.to_cbor_obj() for result in target] for target in self.security_results])
        return fields

    def validate(self) -> None:
        if not self.target_blocks:
            raise BPSecValidationError("security block must target at least one block")
        if len(self.target_blocks) != len(set(self.target_blocks)):
            raise BPSecValidationError("security block target list must not contain duplicates")
        if any(target < 0 for target in self.target_blocks):
            raise BPSecValidationError("security block targets must be unsigned block numbers")
        if self.security_context_id < 0:
            raise BPSecValidationError("negative security context IDs are local-only and not valid here")
        self.security_source.validate()
        if self.security_context_flags & ~int(SecurityContextFlags.PARAMETERS_PRESENT):
            raise BPSecValidationError("reserved security context flag bits must be zero")
        if bool(self.security_context_flags & SecurityContextFlags.PARAMETERS_PRESENT) != bool(
            self.security_context_parameters
        ):
            raise BPSecValidationError("security context parameter flag does not match parameter presence")
        if len(self.security_results) != len(self.target_blocks):
            raise BPSecValidationError("security results must align one-to-one with security targets")


def bib_block(
    block_number: int,
    asb: AbstractSecurityBlock,
    flags: int = 0,
    crc_type: CRCType = CRCType.CRC16_X25,
) -> CanonicalBlock:
    asb.validate()
    return CanonicalBlock(
        block_type_code=BlockType.BIB,
        block_number=block_number,
        block_control_flags=flags,
        crc_type=crc_type,
        data=cbor_encode(asb.to_cbor_obj()),
        parsed_data=asb,
    )


def bcb_block(
    block_number: int,
    asb: AbstractSecurityBlock,
    flags: int = 0,
    crc_type: CRCType = CRCType.CRC16_X25,
) -> CanonicalBlock:
    asb.validate()
    return CanonicalBlock(
        block_type_code=BlockType.BCB,
        block_number=block_number,
        block_control_flags=flags,
        crc_type=crc_type,
        data=cbor_encode(asb.to_cbor_obj()),
        parsed_data=asb,
    )


def _security_blocks(bundle: Bundle, block_type: BlockType | None = None) -> list[CanonicalBlock]:
    blocks = [
        block
        for block in bundle.blocks
        if block.block_type_code in (BlockType.BIB, BlockType.BCB)
    ]
    if block_type is not None:
        blocks = [block for block in blocks if block.block_type_code == block_type]
    return blocks


def _block_type_by_number(bundle: Bundle) -> dict[int, int]:
    mapping = {PRIMARY_BLOCK_NUMBER: PRIMARY_BLOCK_NUMBER}
    for block in bundle.blocks:
        mapping[block.block_number] = block.block_type_code
    return mapping


def validate_bcb_band_policy(bundle: Bundle, band: BandType | str | None) -> None:
    """Reject BCB confidentiality blocks on bands where encryption is illegal."""
    if band is None:
        return
    policy = encryption_policy_for_band(band)
    if policy.encryption_allowed:
        return
    if _security_blocks(bundle, BlockType.BCB):
        raise BPSecValidationError(policy.reason)


def validate_security_blocks(bundle: Bundle, band: BandType | str | None = None) -> None:
    """
    Validate BIB/BCB relationships for a received or locally produced bundle.
    """
    bundle.validate()
    security_blocks = _security_blocks(bundle)
    if not security_blocks:
        return
    validate_bcb_band_policy(bundle, band)
    if bundle.primary.is_fragment():
        raise BPSecValidationError("BIB and BCB blocks must not be added to fragmentary bundles")

    block_types = _block_type_by_number(bundle)
    operations: set[tuple[int, int]] = set()
    bib_targets_by_block: dict[int, set[int]] = {}
    bcb_targets_by_block: dict[int, set[int]] = {}

    for block in security_blocks:
        asb = block.parsed_data
        if not isinstance(asb, AbstractSecurityBlock):
            raise BPSecValidationError("security block must carry parsed AbstractSecurityBlock data")
        asb.validate()
        missing = [target for target in asb.target_blocks if target not in block_types]
        if missing:
            raise BPSecValidationError(f"security block targets missing bundle blocks: {missing}")
        for target in asb.target_blocks:
            op = (block.block_type_code, target)
            if op in operations:
                raise BPSecValidationError("duplicate security operation for the same block target")
            operations.add(op)
        if block.block_type_code == BlockType.BIB:
            bib_targets_by_block[block.block_number] = set(asb.target_blocks)
        elif block.block_type_code == BlockType.BCB:
            bcb_targets_by_block[block.block_number] = set(asb.target_blocks)

    for bib in _security_blocks(bundle, BlockType.BIB):
        targets = bib_targets_by_block[bib.block_number]
        for target in targets:
            if block_types[target] in (BlockType.BIB, BlockType.BCB):
                raise BPSecValidationError("BIBs must not target BIB or BCB security blocks")

    for bcb in _security_blocks(bundle, BlockType.BCB):
        targets = bcb_targets_by_block[bcb.block_number]
        if PRIMARY_BLOCK_NUMBER in targets:
            raise BPSecValidationError("BCBs must not target the primary block")
        if any(block_types[target] == BlockType.BCB for target in targets):
            raise BPSecValidationError("BCBs must not target other BCBs")
        if PAYLOAD_BLOCK_NUMBER in targets and not (
            bcb.block_control_flags & BlockControlFlags.REPLICATE_IN_EVERY_FRAGMENT
        ):
            raise BPSecValidationError("BCBs targeting the payload must be replicated in every fragment")
        if bcb.block_control_flags & BlockControlFlags.DISCARD_BLOCK_IF_UNPROCESSABLE:
            raise BPSecValidationError("BCBs must not be discarded if they cannot be processed")

    for bcb_number, bcb_targets in bcb_targets_by_block.items():
        for bib_number, bib_targets in bib_targets_by_block.items():
            overlap = bcb_targets & bib_targets
            if not overlap:
                continue
            if overlap != bib_targets:
                raise BPSecValidationError(
                    "a BCB must not encrypt only a subset of a multi-target BIB; split the BIB first"
                )
            if bib_number not in bcb_targets:
                raise BPSecValidationError(
                    "a BCB sharing targets with a BIB must also encrypt that BIB"
                )


def security_processing_order(
    bundle: Bundle,
    band: BandType | str | None = None,
) -> list[CanonicalBlock]:
    """
    Return deterministic security-processing order for security blocks.

    RFC 9172 requires BCBs to be evaluated before BIBs when they share a
    target. A stable BCB-then-BIB, block-number order satisfies that rule and
    keeps behavior deterministic across nodes.
    """
    validate_security_blocks(bundle, band=band)
    return sorted(
        _security_blocks(bundle),
        key=lambda block: (0 if block.block_type_code == BlockType.BCB else 1, block.block_number),
    )
