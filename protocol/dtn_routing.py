"""
OpenOrbitLink DTN Routing -- Multi-Hop Store-and-Forward Routing

Implements Epidemic and Spray-and-Wait routing for DTN mesh relay
across ground stations, LoRa nodes, and satellite hops.

Strategies:
  DIRECT:        Only forward to final destination
  EPIDEMIC:      Flood to all encountered nodes (high delivery, high overhead)
  SPRAY_AND_WAIT: L copies in spray phase, then direct delivery (balanced)

Usage:
    router = DTNRouter(strategy=DTNRouter.Strategy.SPRAY_AND_WAIT, spray_copies=4)
    
    # When encountering a neighbor node
    bundles_to_send = router.on_encounter(neighbor_id, neighbor_summary_vector)
    
    # When receiving a bundle
    is_new = router.on_receive(bundle)
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

logger = logging.getLogger("OpenOrbitLink.DTNRouting")


class RoutingStrategy(IntEnum):
    """DTN routing strategy selection."""
    DIRECT = 0         # Only forward to destination
    EPIDEMIC = 1       # Flood to all encountered nodes
    SPRAY_AND_WAIT = 2 # L copies, then direct delivery


@dataclass
class RoutingEntry:
    """Metadata for a bundle in the routing table."""
    bundle_id: str
    destination: str
    copies_remaining: int = 1
    hop_count: int = 0
    max_hops: int = 5
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    forwarded_to: set[str] = field(default_factory=set)
    source_node: str = ""
    payload_size: int = 0
    priority: int = 2

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0.0:
            return False
        return time.time() > self.expires_at

    @property
    def can_forward(self) -> bool:
        return not self.is_expired and self.hop_count < self.max_hops


@dataclass
class NeighborInfo:
    """Information about a discovered neighbor node."""
    node_id: str
    last_seen: float = field(default_factory=time.time)
    encounter_count: int = 1
    bundles_exchanged: int = 0
    link_quality: float = 1.0  # 0.0 to 1.0


class DTNRouter:
    """
    Multi-hop DTN routing engine.

    Manages bundle forwarding decisions based on the selected routing
    strategy. Maintains a routing table, neighbor discovery cache,
    and summary vector for anti-entropy exchange.
    """

    Strategy = RoutingStrategy

    def __init__(
        self,
        node_id: str = "",
        strategy: RoutingStrategy = RoutingStrategy.SPRAY_AND_WAIT,
        spray_copies: int = 4,
        max_hops: int = 5,
        bundle_ttl_s: float = 86400.0,
    ):
        self.node_id = node_id or hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
        self.strategy = strategy
        self.spray_copies = spray_copies
        self.max_hops = max_hops
        self.bundle_ttl_s = bundle_ttl_s

        # Routing table: bundle_id -> RoutingEntry
        self.routing_table: dict[str, RoutingEntry] = {}

        # Neighbor cache: node_id -> NeighborInfo
        self.neighbors: dict[str, NeighborInfo] = {}

        # Delivered bundles (for deduplication)
        self._delivered: set[str] = set()

        # Statistics
        self.stats = {
            "bundles_originated": 0,
            "bundles_received": 0,
            "bundles_forwarded": 0,
            "bundles_delivered": 0,
            "bundles_dropped": 0,
            "encounters": 0,
            "duplicates_suppressed": 0,
        }

    @property
    def summary_vector(self) -> set[str]:
        """Set of bundle IDs this node currently holds (for anti-entropy)."""
        return set(self.routing_table.keys()) | self._delivered

    def originate(
        self,
        bundle_id: str,
        destination: str,
        payload_size: int = 0,
        priority: int = 2,
    ) -> RoutingEntry:
        """
        Register a new locally-originated bundle for routing.

        Args:
            bundle_id: Unique bundle identifier
            destination: Target node/device ID
            payload_size: Size of payload in bytes
            priority: Priority level (0=highest)

        Returns:
            RoutingEntry for the bundle
        """
        copies = self.spray_copies if self.strategy == RoutingStrategy.SPRAY_AND_WAIT else 1

        entry = RoutingEntry(
            bundle_id=bundle_id,
            destination=destination,
            copies_remaining=copies,
            hop_count=0,
            max_hops=self.max_hops,
            expires_at=time.time() + self.bundle_ttl_s if self.bundle_ttl_s > 0 else 0.0,
            source_node=self.node_id,
            payload_size=payload_size,
            priority=priority,
        )

        self.routing_table[bundle_id] = entry
        self.stats["bundles_originated"] += 1
        logger.debug(f"Originated bundle {bundle_id[:8]}... -> {destination[:8]}... copies={copies}")

        return entry

    def on_receive(self, bundle_id: str, source_node: str, destination: str) -> bool:
        """
        Handle reception of a bundle from another node.

        Args:
            bundle_id: Bundle identifier
            source_node: Node that sent this bundle
            destination: Final destination

        Returns:
            True if this is a new bundle (not duplicate)
        """
        # Check if already delivered or known
        if bundle_id in self._delivered:
            self.stats["duplicates_suppressed"] += 1
            return False

        if bundle_id in self.routing_table:
            self.stats["duplicates_suppressed"] += 1
            return False

        self.stats["bundles_received"] += 1

        # Check if this bundle is for us
        if destination == self.node_id:
            self._delivered.add(bundle_id)
            self.stats["bundles_delivered"] += 1
            logger.info(f"Bundle {bundle_id[:8]}... delivered to us")
            return True

        # Store for forwarding
        entry = RoutingEntry(
            bundle_id=bundle_id,
            destination=destination,
            copies_remaining=1,
            hop_count=1,
            max_hops=self.max_hops,
            expires_at=time.time() + self.bundle_ttl_s if self.bundle_ttl_s > 0 else 0.0,
            source_node=source_node,
        )
        entry.forwarded_to.add(source_node)

        self.routing_table[bundle_id] = entry
        logger.debug(f"Stored bundle {bundle_id[:8]}... for forwarding -> {destination[:8]}...")
        return True

    def should_forward(self, bundle_id: str, neighbor_id: str) -> bool:
        """
        Decide whether to forward a bundle to a specific neighbor.

        Args:
            bundle_id: Bundle to consider forwarding
            neighbor_id: Potential next-hop neighbor

        Returns:
            True if the bundle should be forwarded to this neighbor
        """
        entry = self.routing_table.get(bundle_id)
        if entry is None or not entry.can_forward:
            return False

        # Never send back to the source
        if neighbor_id == entry.source_node:
            return False

        # Never send to a node that already has it
        if neighbor_id in entry.forwarded_to:
            return False

        if self.strategy == RoutingStrategy.DIRECT:
            return neighbor_id == entry.destination

        elif self.strategy == RoutingStrategy.EPIDEMIC:
            return True  # Send to everyone

        elif self.strategy == RoutingStrategy.SPRAY_AND_WAIT:
            if entry.copies_remaining > 1:
                # Spray phase: forward with half the copies
                return True
            else:
                # Wait phase: only forward to destination
                return neighbor_id == entry.destination

        return False

    def on_encounter(self, neighbor_id: str, neighbor_summary: set[str]) -> list[str]:
        """
        Handle encounter with a neighbor node.

        Performs anti-entropy exchange: determines which bundles
        the neighbor is missing and should receive.

        Args:
            neighbor_id: ID of the encountered neighbor
            neighbor_summary: Set of bundle IDs the neighbor already has

        Returns:
            List of bundle_ids to forward to this neighbor
        """
        self.stats["encounters"] += 1

        # Update neighbor cache
        if neighbor_id in self.neighbors:
            self.neighbors[neighbor_id].last_seen = time.time()
            self.neighbors[neighbor_id].encounter_count += 1
        else:
            self.neighbors[neighbor_id] = NeighborInfo(node_id=neighbor_id)

        # Determine bundles to forward
        to_forward: list[str] = []

        for bundle_id, entry in list(self.routing_table.items()):
            # Skip expired bundles
            if entry.is_expired:
                del self.routing_table[bundle_id]
                self.stats["bundles_dropped"] += 1
                continue

            # Skip if neighbor already has it
            if bundle_id in neighbor_summary:
                continue

            if self.should_forward(bundle_id, neighbor_id):
                to_forward.append(bundle_id)

                # Update forwarding state
                entry.forwarded_to.add(neighbor_id)
                entry.hop_count += 1

                if self.strategy == RoutingStrategy.SPRAY_AND_WAIT and entry.copies_remaining > 1:
                    # Binary Spray: give half the copies
                    give = entry.copies_remaining // 2
                    entry.copies_remaining -= give

                self.stats["bundles_forwarded"] += 1

        # Sort by priority (SOS first)
        to_forward.sort(key=lambda bid: self.routing_table.get(bid, RoutingEntry(bundle_id=bid, destination="")).priority)

        if to_forward:
            logger.info(f"Encounter with {neighbor_id[:8]}...: forwarding {len(to_forward)} bundles")

        return to_forward

    def prune_expired(self) -> int:
        """Remove expired bundles from routing table. Returns count removed."""
        expired = [bid for bid, entry in self.routing_table.items() if entry.is_expired]
        for bid in expired:
            del self.routing_table[bid]
        self.stats["bundles_dropped"] += len(expired)
        return len(expired)

    def get_stats(self) -> dict:
        """Return routing statistics."""
        return {
            **self.stats,
            "node_id": self.node_id,
            "strategy": self.strategy.name,
            "routing_table_size": len(self.routing_table),
            "neighbor_count": len(self.neighbors),
            "delivered_count": len(self._delivered),
        }
