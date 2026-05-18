from __future__ import annotations

"""
OpenOrbitLink Mesh Routing — LoRa + BLE Mesh Network Layer

Implements the mesh routing decision engine that enables multi-hop
message relay between OpenOrbitLink nodes via LoRa and Bluetooth Low Energy.
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List, Dict

from .license import LicenseGate
from .packet import TransmitBand


class NodeCapability(IntEnum):
    """Capabilities a mesh node can advertise."""
    TEXT_ONLY = 0x01
    VOICE = 0x02
    SDR_RECEIVE = 0x04
    SDR_TRANSMIT = 0x08
    SATELLITE_DIRECT = 0x10
    GROUND_STATION = 0x20
    LORA_RELAY = 0x40
    INTERNET_GATEWAY = 0x80


@dataclass
class MeshNode:
    """A discovered peer in the mesh network."""
    node_id: bytes                    # 6-byte device ID
    capabilities: int = 0x01          # Bitmask of NodeCapability
    last_seen: float = 0.0            # Unix timestamp
    rssi_dbm: float = -100.0          # Signal strength
    hop_count: int = 0                # Hops from this node
    has_satellite_access: bool = False
    has_internet: bool = False
    callsign: str = ""
    license_confirmed: bool = False
    bands: tuple[TransmitBand, ...] = (TransmitBand.ISM,)
    latitude: float = 0.0
    longitude: float = 0.0
    battery_percent: int = 100

    @property
    def is_alive(self) -> bool:
        """Node considered alive if seen in last 10 minutes."""
        return (time.time() - self.last_seen) < 600

    @property
    def link_quality(self) -> float:
        """Link quality score 0-1 based on RSSI and freshness."""
        rssi_score = max(0, min(1, (self.rssi_dbm + 120) / 80))
        age = time.time() - self.last_seen
        freshness = max(0, 1 - age / 600)
        return 0.6 * rssi_score + 0.4 * freshness

    def can_transmit_on(self, band: TransmitBand, encrypted: bool = False) -> bool:
        if band not in self.bands:
            return False
        gate = LicenseGate(self.callsign, license_confirmed=self.license_confirmed)
        return gate.authorize(band, encrypted=encrypted).allowed


@dataclass
class RouteEntry:
    """Routing table entry for reaching a destination node."""
    destination_id: bytes
    next_hop_id: bytes
    hop_count: int
    metric: float               # Lower = better
    last_updated: float = 0.0
    expires_at: float = 0.0


class MeshRouter:
    """
    OpenOrbitLink mesh routing engine.

    Routing priority:
    1. Direct satellite upload (if node has TX capability + sat visible)
    2. Relay to neighbor with satellite access
    3. Multi-hop toward nearest ground station
    4. Store locally, retry on next satellite pass

    Uses a simplified distance-vector protocol with satellite-awareness.
    """

    def __init__(
        self,
        local_id: bytes,
        capabilities: int = 0x41,
        callsign: str = "",
        license_confirmed: bool = False,
    ):
        self.local_id = local_id
        self.capabilities = capabilities
        self.callsign = callsign
        self.license_gate = LicenseGate(callsign, license_confirmed=license_confirmed)
        self.neighbors: Dict[bytes, MeshNode] = {}
        self.routing_table: Dict[bytes, RouteEntry] = {}
        self._message_seen: set = set()  # Dedup by hash
        self._max_seen = 10000

    def add_neighbor(self, node: MeshNode):
        """Register or update a discovered neighbor."""
        self.neighbors[node.node_id] = node
        node.last_seen = time.time()

        # Update routing table
        self.routing_table[node.node_id] = RouteEntry(
            destination_id=node.node_id,
            next_hop_id=node.node_id,
            hop_count=1,
            metric=1.0 - node.link_quality,
            last_updated=time.time(),
            expires_at=time.time() + 600,
        )

    def remove_stale_neighbors(self):
        """Purge neighbors not seen recently."""
        stale = [nid for nid, n in self.neighbors.items() if not n.is_alive]
        for nid in stale:
            del self.neighbors[nid]
            if nid in self.routing_table:
                del self.routing_table[nid]

    def find_best_route(
        self,
        destination_id: Optional[bytes] = None,
        satellite_visible: bool = False,
        priority: int = 2,
        transmit_band: TransmitBand | str = TransmitBand.ISM,
        encrypted: bool = False,
    ) -> Optional[str]:
        """
        Determine best routing action for a message.

        Returns action string:
        - "satellite_direct" — transmit directly to satellite
        - "relay:<node_id_hex>" — relay to specific neighbor
        - "store" — store locally for later
        """
        self.remove_stale_neighbors()
        band = TransmitBand.from_value(transmit_band)
        local_decision = self.license_gate.authorize(band, encrypted=encrypted)
        if not local_decision.allowed:
            return "blocked:" + local_decision.reason

        # Strategy 1: Direct satellite if we can
        has_tx = bool(self.capabilities & NodeCapability.SDR_TRANSMIT)
        has_sat = bool(self.capabilities & NodeCapability.SATELLITE_DIRECT)
        if satellite_visible and (has_tx or has_sat):
            return "satellite_direct"

        # Strategy 2: Find neighbor with satellite access
        sat_neighbors = [
            n for n in self.neighbors.values()
            if n.is_alive and n.has_satellite_access and n.can_transmit_on(band, encrypted=encrypted)
        ]
        if sat_neighbors:
            best = max(sat_neighbors, key=lambda n: n.link_quality)
            return "relay:" + best.node_id.hex()

        # Strategy 3: Find neighbor closer to a ground station
        gs_neighbors = [
            n for n in self.neighbors.values()
            if (
                n.is_alive
                and (n.capabilities & NodeCapability.GROUND_STATION)
                and n.can_transmit_on(band, encrypted=encrypted)
            )
        ]
        if gs_neighbors:
            best = max(gs_neighbors, key=lambda n: n.link_quality)
            return "relay:" + best.node_id.hex()

        # Strategy 4: Find any relay-capable neighbor (flood toward gateway)
        relay_neighbors = [
            n for n in self.neighbors.values()
            if n.is_alive and (n.capabilities & NodeCapability.LORA_RELAY) and n.can_transmit_on(band, encrypted=encrypted)
        ]
        if relay_neighbors:
            best = max(relay_neighbors, key=lambda n: n.link_quality)
            return "relay:" + best.node_id.hex()

        # No route available — store for later
        return "store"

    def should_relay(self, packet_hash: bytes) -> bool:
        """Check if we should relay a packet (dedup)."""
        h = packet_hash[:16]
        if h in self._message_seen:
            return False
        self._message_seen.add(h)
        if len(self._message_seen) > self._max_seen:
            # Evict oldest (approximate)
            self._message_seen = set(list(self._message_seen)[-5000:])
        return True

    def get_network_status(self) -> dict:
        """Get mesh network status summary."""
        alive = [n for n in self.neighbors.values() if n.is_alive]
        return {
            "local_id": self.local_id.hex(),
            "capabilities": self.capabilities,
            "callsign": self.callsign,
            "total_neighbors": len(self.neighbors),
            "alive_neighbors": len(alive),
            "routes": len(self.routing_table),
            "sat_capable_neighbors": sum(
                1 for n in alive if n.has_satellite_access
            ),
            "ground_station_neighbors": sum(
                1 for n in alive
                if n.capabilities & NodeCapability.GROUND_STATION
            ),
        }
