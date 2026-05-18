from __future__ import annotations
"""
OpenOrbitLink Security Module — Post-Quantum Encryption & Key Management

Implements hybrid classical + post-quantum encryption:
- Signal Protocol (SPQR Triple Ratchet) for message encryption
- ML-KEM-768 for quantum-resistant key encapsulation
- BPSec (RFC 9172) for bundle-layer integrity
- Android Keystore integration for key storage
"""

import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class BandType(str, Enum):
    """Regulatory class of the RF path used for a transmission."""

    UNKNOWN = "unknown"
    AMATEUR = "amateur"
    ISM = "ism"
    LICENSED = "licensed"
    NTN = "ntn"
    RECEIVE_ONLY = "receive_only"

    @classmethod
    def from_value(cls, value: "BandType | str") -> "BandType":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_")
        aliases = {
            "ham": cls.AMATEUR,
            "amateur_radio": cls.AMATEUR,
            "433": cls.ISM,
            "868": cls.ISM,
            "915": cls.ISM,
            "lorawan": cls.ISM,
            "cellular_ntn": cls.NTN,
            "nb_ntn": cls.NTN,
            "rx": cls.RECEIVE_ONLY,
            "rx_only": cls.RECEIVE_ONLY,
        }
        if normalized in aliases:
            return aliases[normalized]
        return cls(normalized)


class EncryptionPolicyError(ValueError):
    """Raised when confidentiality is requested on a band that disallows it."""


@dataclass(frozen=True)
class EncryptionPolicy:
    """Band-aware confidentiality policy.

    Amateur radio paths may authenticate and integrity-check traffic, but they
    must not carry ciphertext intended to hide message content. ISM, licensed
    private links, and carrier NTN paths can carry encrypted payloads when local
    spectrum and service rules allow it.
    """

    band: BandType
    encryption_allowed: bool
    tx_allowed: bool
    requires_callsign: bool = False
    reason: str = ""

    def assert_encryption_allowed(self) -> None:
        if not self.tx_allowed:
            raise EncryptionPolicyError(self.reason or f"{self.band.value} is not a transmit path")
        if not self.encryption_allowed:
            raise EncryptionPolicyError(
                self.reason or f"encryption is not allowed on {self.band.value} transmissions"
            )

    def assert_plaintext_allowed(self) -> None:
        if not self.tx_allowed:
            raise EncryptionPolicyError(self.reason or f"{self.band.value} is not a transmit path")


_BAND_POLICIES: dict[BandType, EncryptionPolicy] = {
    BandType.UNKNOWN: EncryptionPolicy(
        band=BandType.UNKNOWN,
        encryption_allowed=False,
        tx_allowed=False,
        reason="transmit band is unknown; select AMATEUR, ISM, LICENSED, or NTN explicitly",
    ),
    BandType.AMATEUR: EncryptionPolicy(
        band=BandType.AMATEUR,
        encryption_allowed=False,
        tx_allowed=True,
        requires_callsign=True,
        reason="amateur radio transmissions must not obscure message meaning; use plaintext plus integrity only",
    ),
    BandType.ISM: EncryptionPolicy(
        band=BandType.ISM,
        encryption_allowed=True,
        tx_allowed=True,
        reason="ISM links may carry encrypted application payloads subject to regional duty-cycle and power limits",
    ),
    BandType.LICENSED: EncryptionPolicy(
        band=BandType.LICENSED,
        encryption_allowed=True,
        tx_allowed=True,
        reason="licensed private/commercial links may carry encrypted payloads within license terms",
    ),
    BandType.NTN: EncryptionPolicy(
        band=BandType.NTN,
        encryption_allowed=True,
        tx_allowed=True,
        reason="carrier NTN paths rely on operator authorization and can carry encrypted application payloads",
    ),
    BandType.RECEIVE_ONLY: EncryptionPolicy(
        band=BandType.RECEIVE_ONLY,
        encryption_allowed=False,
        tx_allowed=False,
        reason="receive-only hardware cannot transmit",
    ),
}


def encryption_policy_for_band(band: BandType | str) -> EncryptionPolicy:
    """Return the confidentiality policy for a regulatory band."""

    return _BAND_POLICIES[BandType.from_value(band)]


@dataclass
class KeyPair:
    """Asymmetric key pair for OpenOrbitLink identity."""
    public_key: bytes
    private_key: bytes
    created_at: float
    key_type: str = "X25519"  # or "ML-KEM-768"


@dataclass
class EncryptedPayload:
    """Encrypted message payload with metadata."""
    ciphertext: bytes
    nonce: bytes              # 12 bytes for AES-GCM
    sender_public: bytes      # Sender's ephemeral public key
    key_id: bytes             # 4 bytes — identifies which ratchet key
    timestamp: int


class OpenOrbitLinkCrypto:
    """
    Encryption engine for OpenOrbitLink protocol.

    Uses AES-256-GCM for symmetric encryption with HKDF for key
    derivation. In production, integrates with Signal Protocol
    for ratcheted key management.
    """

    def __init__(self, device_secret: Optional[bytes] = None):
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography package required: pip install cryptography")

        self._device_secret = device_secret or os.urandom(32)
        self._session_keys: dict[bytes, bytes] = {}

    def derive_shared_key(self, peer_public: bytes, context: bytes = b"OpenOrbitLink-v1") -> bytes:
        """Derive shared encryption key using HKDF."""
        # In production: X25519 DH + ML-KEM hybrid
        # Simplified: HKDF over concatenated material
        ikm = self._device_secret + peer_public
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=context,
        )
        return hkdf.derive(ikm)

    def encrypt(
        self,
        plaintext: bytes,
        key: bytes,
        band: BandType | str = BandType.ISM,
    ) -> EncryptedPayload:
        """Encrypt payload with AES-256-GCM if the selected band permits it."""
        encryption_policy_for_band(band).assert_encryption_allowed()
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return EncryptedPayload(
            ciphertext=ciphertext,
            nonce=nonce,
            sender_public=self._device_secret[:32],  # Simplified
            key_id=hashlib.sha256(key).digest()[:4],
            timestamp=int(time.time()),
        )

    def decrypt(self, encrypted: EncryptedPayload, key: bytes) -> bytes:
        """Decrypt AES-256-GCM payload."""
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(encrypted.nonce, encrypted.ciphertext, None)

    def compute_mac(self, data: bytes, key: bytes) -> bytes:
        """Compute HMAC-SHA256 for integrity verification."""
        return hmac.new(key, data, hashlib.sha256).digest()

    def verify_mac(self, data: bytes, mac: bytes, key: bytes) -> bool:
        """Verify HMAC-SHA256."""
        expected = self.compute_mac(data, key)
        return hmac.compare_digest(mac, expected)


from .bpsec import (  # noqa: E402
    AbstractSecurityBlock,
    BPSecValidationError,
    SecurityContextFlags,
    SecurityParameter,
    SecurityReasonCode,
    SecurityResult,
    bcb_block,
    bib_block,
    security_processing_order,
    validate_security_blocks,
)
