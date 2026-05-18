from __future__ import annotations
"""
OpenOrbitLink DTN — Delay-Tolerant Networking & Store-and-Forward Engine

Implements Bundle Protocol v7 (RFC 9171) concepts adapted for satellite
communication with intermittent connectivity windows of 8-12 minutes.

Key strategies:
- Store messages locally until satellite pass window
- Burst-transmit during visibility windows
- Priority queuing (SOS > Voice > Text > Data)
- ACK tracking with retry logic
- Multi-hop relay through ground station network
"""

import asyncio
import sqlite3
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional, Callable

from .packet import OpenOrbitLinkPacket, PayloadType, OpenOrbitLinkProtocol


class BundleState(IntEnum):
    QUEUED = 0
    TRANSMITTING = 1
    AWAITING_ACK = 2
    DELIVERED = 3
    FAILED = 4
    EXPIRED = 5


@dataclass
class Bundle:
    """DTN Bundle — a message waiting for transmission."""
    bundle_id: str
    packet: OpenOrbitLinkPacket
    state: BundleState = BundleState.QUEUED
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0          # 0 = never expires
    retry_count: int = 0
    max_retries: int = 5
    last_attempt: float = 0.0
    destination: str = ""
    priority: int = 2                # 0=highest

    def __post_init__(self):
        if self.expires_at == 0.0:
            # Default TTL: 24 hours for text, 1 hour for voice, never for SOS
            ttl_map = {
                PayloadType.SOS: 0,        # Never expires
                PayloadType.VOICE: 3600,
                PayloadType.TEXT: 86400,
                PayloadType.RELAY: 86400,
                PayloadType.ACK: 7200,
                PayloadType.BEACON: 600,
            }
            ttl = ttl_map.get(self.packet.payload_type, 86400)
            self.expires_at = self.created_at + ttl if ttl > 0 else 0.0

        # Set priority from packet type
        prio_map = {
            PayloadType.SOS: 0,
            PayloadType.VOICE: 1,
            PayloadType.TEXT: 2,
            PayloadType.RELAY: 3,
            PayloadType.ACK: 1,
            PayloadType.BEACON: 4,
        }
        self.priority = prio_map.get(self.packet.payload_type, 2)

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0.0:
            return False
        return time.time() > self.expires_at

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries and not self.is_expired


class BundleStore:
    """
    Persistent bundle storage using SQLite.
    Stores messages for delay-tolerant forwarding.
    """

    def __init__(self, db_path: str = "OpenOrbitLink_bundles.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bundles (
                    bundle_id TEXT PRIMARY KEY,
                    packet_data BLOB NOT NULL,
                    state INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 2,
                    created_at REAL NOT NULL,
                    expires_at REAL DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    last_attempt REAL DEFAULT 0,
                    destination TEXT DEFAULT '',
                    payload_type INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_state_priority
                ON bundles(state, priority, created_at)
            """)

    def store(self, bundle: Bundle):
        """Store a bundle for later transmission."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO bundles
                   (bundle_id, packet_data, state, priority, created_at,
                    expires_at, retry_count, max_retries, last_attempt,
                    destination, payload_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bundle.bundle_id,
                    bundle.packet.serialize(),
                    int(bundle.state),
                    bundle.priority,
                    bundle.created_at,
                    bundle.expires_at,
                    bundle.retry_count,
                    bundle.max_retries,
                    bundle.last_attempt,
                    bundle.destination,
                    int(bundle.packet.payload_type),
                )
            )

    def get_pending(self, limit: int = 50) -> list[dict]:
        """Get pending bundles sorted by priority then age."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM bundles
                   WHERE state IN (0, 2)
                   ORDER BY priority ASC, created_at ASC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_state(self, bundle_id: str, state: BundleState, retry_inc: bool = False):
        """Update bundle state."""
        with sqlite3.connect(self.db_path) as conn:
            if retry_inc:
                conn.execute(
                    """UPDATE bundles SET state=?, retry_count=retry_count+1,
                       last_attempt=? WHERE bundle_id=?""",
                    (int(state), time.time(), bundle_id)
                )
            else:
                conn.execute(
                    "UPDATE bundles SET state=? WHERE bundle_id=?",
                    (int(state), bundle_id)
                )

    def cleanup_expired(self) -> int:
        """Remove expired bundles. Returns count removed."""
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """DELETE FROM bundles
                   WHERE expires_at > 0 AND expires_at < ?
                   AND state NOT IN (3)""",
                (now,)
            )
            return cursor.rowcount

    def get_stats(self) -> dict:
        """Get bundle store statistics."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            for state in BundleState:
                count = conn.execute(
                    "SELECT COUNT(*) FROM bundles WHERE state=?",
                    (int(state),)
                ).fetchone()[0]
                stats[state.name] = count
            stats["total"] = sum(stats.values())
            return stats


class DTNEngine:
    """
    Delay-Tolerant Networking engine for OpenOrbitLink.

    Manages the lifecycle of messages through:
    1. Queue → store in bundle DB
    2. Wait for satellite pass window
    3. Burst-transmit during visibility (8-12 min)
    4. Track ACKs, retry on failure
    5. Relay through mesh network if available
    """

    def __init__(
        self,
        protocol: OpenOrbitLinkProtocol,
        db_path: str = "OpenOrbitLink_bundles.db",
        on_transmit: Optional[Callable] = None,
    ):
        self.protocol = protocol
        self.store = BundleStore(db_path)
        self._on_transmit = on_transmit
        self._running = False
        self._bundle_counter = 0

    def queue_message(self, packet: OpenOrbitLinkPacket, destination: str = "") -> str:
        """Queue a message for satellite transmission."""
        self._bundle_counter += 1
        bundle_id = f"FS-{int(time.time())}-{self._bundle_counter:06d}"

        bundle = Bundle(
            bundle_id=bundle_id,
            packet=packet,
            destination=destination,
        )
        self.store.store(bundle)
        return bundle_id

    def queue_text(self, text: str, destination: str = "") -> str:
        """Convenience: queue a text message."""
        packet = self.protocol.create_text_message(text)
        return self.queue_message(packet, destination)

    def queue_sos(self, lat: float, lon: float, message: str = "") -> str:
        """Queue emergency SOS — highest priority."""
        packet = self.protocol.create_sos(lat, lon, message)
        return self.queue_message(packet)

    async def transmission_window(self, duration_seconds: float = 600.0):
        """
        Execute burst transmission during a satellite visibility window.

        Sends queued messages in priority order until window closes
        or queue is empty.
        """
        start = time.time()
        transmitted = 0
        self.store.cleanup_expired()

        pending = self.store.get_pending()

        for bundle_data in pending:
            elapsed = time.time() - start
            if elapsed >= duration_seconds:
                break

            bundle_id = bundle_data["bundle_id"]
            raw = bundle_data["packet_data"]

            # Mark as transmitting
            self.store.update_state(bundle_id, BundleState.TRANSMITTING)

            # Transmit
            if self._on_transmit:
                try:
                    success = await self._on_transmit(raw)
                    if success:
                        self.store.update_state(bundle_id, BundleState.AWAITING_ACK)
                        transmitted += 1
                    else:
                        self.store.update_state(
                            bundle_id, BundleState.QUEUED, retry_inc=True
                        )
                except Exception:
                    self.store.update_state(
                        bundle_id, BundleState.QUEUED, retry_inc=True
                    )
            else:
                # No transmitter — simulate
                self.store.update_state(bundle_id, BundleState.AWAITING_ACK)
                transmitted += 1

            # Brief pause between packets
            await asyncio.sleep(0.1)

        return transmitted

    def receive_ack(self, ack_bundle_id: str):
        """Process received ACK — mark bundle as delivered."""
        self.store.update_state(ack_bundle_id, BundleState.DELIVERED)

    def get_stats(self) -> dict:
        """Get DTN engine statistics."""
        return self.store.get_stats()

