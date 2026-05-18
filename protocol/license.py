from __future__ import annotations

"""
Callsign and transmit-authorization helpers.

This module does not claim to verify a government license database. It provides
local guardrails: syntactic callsign checks, explicit user/operator attestation,
and band-aware policy decisions that prevent accidental amateur-band TX.
"""

import re
import time
from dataclasses import dataclass
from typing import Optional

from security import BandType, encryption_policy_for_band
from .packet import TransmitBand


class CallsignError(ValueError):
    """Raised when a callsign is malformed or missing for a guarded TX path."""


class LicenseGateError(PermissionError):
    """Raised when a transmission is not authorized by local policy."""


@dataclass(frozen=True)
class CallsignRecord:
    callsign: str
    country: str = "unknown"
    verified: bool = False
    verified_at: float = 0.0


@dataclass(frozen=True)
class LicenseDecision:
    allowed: bool
    reason: str
    callsign: str = ""
    requires_callsign: bool = False

    def assert_allowed(self) -> None:
        if not self.allowed:
            raise LicenseGateError(self.reason)


class CallsignValidator:
    """Validate AX.25-compatible amateur callsigns used by APRS/packet radio."""

    AX25_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-[0-9]{1,2})?$")
    INDIA_RE = re.compile(r"^VU[23][A-Z]{2,3}(?:-[0-9]{1,2})?$")
    US_RE = re.compile(r"^[AKNW][A-Z0-9]{1,5}(?:-[0-9]{1,2})?$")

    @classmethod
    def normalize(cls, callsign: str) -> str:
        value = callsign.strip().upper()
        if not value:
            raise CallsignError("callsign is required for amateur-band transmission")
        if not cls.AX25_RE.fullmatch(value):
            raise CallsignError(f"invalid AX.25 callsign: {callsign!r}")
        ssid = value.split("-", 1)[1] if "-" in value else None
        if ssid is not None and not 0 <= int(ssid) <= 15:
            raise CallsignError("AX.25 SSID must be in the range 0..15")
        return value

    @classmethod
    def looks_like_country(cls, callsign: str, country: str | None) -> bool:
        normalized = cls.normalize(callsign)
        country_key = (country or "").strip().upper()
        if country_key in {"IN", "IND", "INDIA"}:
            return bool(cls.INDIA_RE.fullmatch(normalized))
        if country_key in {"US", "USA", "UNITED STATES"}:
            return bool(cls.US_RE.fullmatch(normalized))
        return True


class LicenseGate:
    """Band-aware local authorization for TX attempts."""

    def __init__(
        self,
        callsign: str = "",
        country: str = "unknown",
        license_confirmed: bool = False,
    ):
        self.callsign = callsign
        self.country = country
        self.license_confirmed = license_confirmed

    def authorize(
        self,
        band: TransmitBand | BandType | str,
        *,
        callsign: Optional[str] = None,
        encrypted: bool = False,
        purpose: str = "data",
    ) -> LicenseDecision:
        transmit_band = TransmitBand.from_value(band)
        policy = encryption_policy_for_band(transmit_band.security_band)
        candidate = callsign if callsign is not None else self.callsign

        if not policy.tx_allowed:
            return LicenseDecision(False, policy.reason)
        if encrypted and not policy.encryption_allowed:
            return LicenseDecision(False, policy.reason)
        if transmit_band != TransmitBand.AMATEUR:
            return LicenseDecision(True, "no amateur license gate required", callsign=candidate or "")

        try:
            normalized = CallsignValidator.normalize(candidate or "")
        except CallsignError as exc:
            return LicenseDecision(False, str(exc), requires_callsign=True)

        if not CallsignValidator.looks_like_country(normalized, self.country):
            return LicenseDecision(
                False,
                f"callsign {normalized} does not match expected country pattern for {self.country}",
                callsign=normalized,
                requires_callsign=True,
            )
        if not self.license_confirmed:
            return LicenseDecision(
                False,
                "operator must confirm a valid amateur radio license before TX",
                callsign=normalized,
                requires_callsign=True,
            )
        if purpose.lower() in {"commercial", "pstn", "paid"}:
            return LicenseDecision(
                False,
                "amateur radio must not be used for commercial or PSTN traffic",
                callsign=normalized,
                requires_callsign=True,
            )
        return LicenseDecision(True, "amateur-band TX authorized by local attestation", callsign=normalized)

    def assert_can_transmit(
        self,
        band: TransmitBand | BandType | str,
        *,
        callsign: Optional[str] = None,
        encrypted: bool = False,
        purpose: str = "data",
    ) -> LicenseDecision:
        decision = self.authorize(band, callsign=callsign, encrypted=encrypted, purpose=purpose)
        decision.assert_allowed()
        return decision

    def record(self) -> CallsignRecord:
        callsign = CallsignValidator.normalize(self.callsign) if self.callsign else ""
        return CallsignRecord(
            callsign=callsign,
            country=self.country,
            verified=self.license_confirmed,
            verified_at=time.time() if self.license_confirmed else 0.0,
        )
