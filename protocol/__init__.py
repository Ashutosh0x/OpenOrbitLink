"""
OpenOrbitLink Protocol Module — Packet format, routing, DTN, mesh networking.

Core protocol combining AX.25 + CCSDS + BPv7 for decentralised
satellite communication over intermittent links.
"""

from .packet import OpenOrbitLinkPacket, OpenOrbitLinkProtocol, PayloadType, TransmitBand, crc16_ccitt, ReedSolomonFEC
from .dtn import DTNEngine, BundleStore, Bundle, BundleState
from .ntn import NTNGatewayBridge, NTNGatewayRequest, NTNGatewayResponse
from .license import CallsignError, CallsignValidator, LicenseDecision, LicenseGate, LicenseGateError
from .fossa import FossaFrame, FossaFrameError, packet_payload_to_fossa_frames
from .bpv7 import (
    Bundle as BPv7Bundle,
    BundleControlFlags,
    CanonicalBlock,
    CRCType,
    CreationTimestamp,
    EndpointID,
    PrimaryBlock,
    payload_block,
)
from .aprs import APRSPacket, APRSPosition, AX25Frame, build_ax25_ui_frame, decode_ax25_ui_frame, parse_aprs_info
