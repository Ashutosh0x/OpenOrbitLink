from __future__ import annotations

"""
Carrier NTN gateway bridge scaffolding.

OpenOrbitLink cannot transmit arbitrary RF through a phone NTN modem. This
module models the future convergence point where a queued DTN bundle is handed
to an operator-controlled satellite messaging/SIP/API gateway.
"""

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from .dtn import Bundle
from .packet import OpenOrbitLinkPacket, TransmitBand


@dataclass(frozen=True)
class NTNGatewayRequest:
    """Serialized DTN bundle plus routing metadata for a carrier NTN gateway."""

    endpoint_url: str
    bundle_id: str
    destination: str
    payload: bytes
    transmit_band: TransmitBand = TransmitBand.CARRIER_NTN
    content_type: str = "application/vnd.openorbitlink.bundle"


@dataclass(frozen=True)
class NTNGatewayResponse:
    """Result returned by a carrier NTN gateway adapter."""

    accepted: bool
    status: str
    gateway_message_id: str = ""
    reason: str = ""


GatewaySubmitter = Callable[[NTNGatewayRequest], Any]


class NTNGatewayBridge:
    """
    Architectural stub for handing OpenOrbitLink DTN bundles to carrier NTN.

    A production adapter would authenticate to a carrier or MVNO endpoint and
    submit the bundle over the operator-approved API/SIP/SCS path. The default
    instance is intentionally non-transmitting: it builds the request and reports
    that no carrier endpoint has been configured.
    """

    def __init__(
        self,
        endpoint_url: str,
        *,
        submitter: GatewaySubmitter | None = None,
    ):
        if not endpoint_url:
            raise ValueError("endpoint_url is required")
        self.endpoint_url = endpoint_url
        self._submitter = submitter

    def build_request(self, bundle: Bundle, destination: str | None = None) -> NTNGatewayRequest:
        """Serialize a DTN bundle for submission to a carrier NTN gateway."""
        if not isinstance(bundle.packet, OpenOrbitLinkPacket):
            raise TypeError("bundle.packet must be an OpenOrbitLinkPacket")

        bundle.packet.transmit_band = TransmitBand.CARRIER_NTN
        bundle.packet.assert_encryption_policy()
        return NTNGatewayRequest(
            endpoint_url=self.endpoint_url,
            bundle_id=bundle.bundle_id,
            destination=destination if destination is not None else bundle.destination,
            payload=bundle.packet.serialize(),
        )

    async def submit_bundle(self, bundle: Bundle, destination: str | None = None) -> NTNGatewayResponse:
        """Submit a bundle when a carrier-specific submitter has been configured."""
        request = self.build_request(bundle, destination=destination)
        if self._submitter is None:
            return NTNGatewayResponse(
                accepted=False,
                status="not_configured",
                reason=(
                    "carrier NTN handoff is a convergence stub; configure a carrier "
                    "SIP/API submitter before transmitting"
                ),
            )

        response = self._submitter(request)
        if inspect.isawaitable(response):
            response = await response
        if isinstance(response, NTNGatewayResponse):
            return response
        if isinstance(response, dict):
            return NTNGatewayResponse(
                accepted=bool(response.get("accepted", False)),
                status=str(response.get("status", "unknown")),
                gateway_message_id=str(response.get("gateway_message_id", "")),
                reason=str(response.get("reason", "")),
            )
        raise TypeError("carrier NTN submitter must return NTNGatewayResponse or dict")
