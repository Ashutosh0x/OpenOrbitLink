"""
OpenOrbitLink Protocol Module — Packet format, routing, DTN, mesh networking.

Core protocol combining AX.25 + CCSDS + BPv7 for decentralised
satellite communication over intermittent links.
"""

from .packet import OpenOrbitLinkPacket, OpenOrbitLinkProtocol, PayloadType, crc16_ccitt, ReedSolomonFEC
from .dtn import DTNEngine, BundleStore, Bundle, BundleState
