"""
OpenOrbitLink Inbox Router -- Satellite Downlink to User Inbox Delivery

Routes packets received via TinyGS satellite downlink or local LoRa
reception to the appropriate user inbox via the FastAPI backend.

Flow:
    Satellite downlink -> TinyGS ground station -> TinyGS API
    -> InboxRouter.poll_and_route() -> decode OOL packet header
    -> extract destination device_id -> POST /api/v1/inbox/deliver
    -> User sees message in Android app

Also supports direct LoRa reception from the ground station's own
SX1276 receiver for local mesh messages.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("OpenOrbitLink.InboxRouter")


@dataclass
class RoutedPacket:
    """A packet that has been routed to a user inbox."""
    packet_hash: str
    source_satellite: str
    destination_id: str
    payload_type: int
    payload_size: int
    rssi: float
    snr: float
    received_at: float
    delivered_at: float = 0.0
    delivery_status: str = "pending"


class InboxRouter:
    """
    Routes received satellite/mesh packets to user inboxes.

    Maintains a deduplication cache to prevent double-delivery of packets
    received by multiple ground stations or during overlapping pass windows.
    """

    def __init__(
        self,
        backend_url: str = "http://localhost:8000",
        api_token: Optional[str] = None,
        dedup_ttl_s: float = 3600.0,
    ):
        self.backend_url = backend_url.rstrip("/")
        self.api_token = api_token
        self.dedup_ttl_s = dedup_ttl_s

        self._seen_hashes: dict[str, float] = {}  # hash -> timestamp
        self._routed_packets: list[RoutedPacket] = []
        self._stats = {
            "total_received": 0,
            "duplicates_skipped": 0,
            "delivered": 0,
            "delivery_failed": 0,
            "unknown_destination": 0,
        }

    def _packet_hash(self, data: bytes) -> str:
        """Compute deduplication hash for a packet."""
        return hashlib.sha256(data).hexdigest()[:16]

    def _is_duplicate(self, data: bytes) -> bool:
        """Check if we've already processed this packet."""
        h = self._packet_hash(data)
        now = time.time()

        # Prune old entries
        self._seen_hashes = {
            k: v for k, v in self._seen_hashes.items()
            if now - v < self.dedup_ttl_s
        }

        if h in self._seen_hashes:
            return True

        self._seen_hashes[h] = now
        return False

    def _decode_ool_header(self, data: bytes) -> Optional[dict]:
        """
        Decode an OpenOrbitLink packet header to extract routing info.

        Header format (21 bytes):
            magic:      2 bytes (0x4F4C = "OL")
            version:    1 byte
            device_id:  8 bytes
            timestamp:  4 bytes
            payload_type: 1 byte
            sequence:   2 bytes
            flags:      1 byte
            band:       1 byte
            payload_len: 1 byte
        """
        import struct

        if len(data) < 21:
            return None

        try:
            magic = struct.unpack(">H", data[0:2])[0]
            if magic != 0x4F4C:  # "OL"
                # Try without magic -- raw payload
                return {
                    "device_id": data[:8].hex(),
                    "payload_type": 0,
                    "payload": data,
                    "raw": True,
                }

            version = data[2]
            device_id = data[3:11].hex()
            timestamp = struct.unpack(">I", data[11:15])[0]
            payload_type = data[15]
            sequence = struct.unpack(">H", data[16:18])[0]
            flags = data[18]
            band = data[19]
            payload_len = data[20]

            payload = data[21:21 + payload_len] if len(data) > 21 else b""

            return {
                "version": version,
                "device_id": device_id,
                "timestamp": timestamp,
                "payload_type": payload_type,
                "sequence": sequence,
                "flags": flags,
                "band": band,
                "payload": payload,
                "raw": False,
            }
        except Exception as e:
            logger.debug(f"Header decode failed: {e}")
            return None

    async def route_packet(
        self,
        packet_data: bytes,
        source_satellite: str = "unknown",
        rssi: float = 0.0,
        snr: float = 0.0,
    ) -> bool:
        """
        Route a single received packet to the appropriate user inbox.

        Args:
            packet_data: Raw packet bytes
            source_satellite: Name of the satellite that relayed the packet
            rssi: Received signal strength
            snr: Signal-to-noise ratio

        Returns:
            True if successfully delivered
        """
        self._stats["total_received"] += 1

        # Deduplication
        if self._is_duplicate(packet_data):
            self._stats["duplicates_skipped"] += 1
            logger.debug(f"Duplicate packet skipped (hash={self._packet_hash(packet_data)})")
            return False

        # Decode header
        header = self._decode_ool_header(packet_data)
        if header is None:
            logger.warning(f"Cannot decode packet header ({len(packet_data)} bytes)")
            self._stats["unknown_destination"] += 1
            return False

        device_id = header["device_id"]
        payload_type = header.get("payload_type", 0)

        logger.info(
            f"Routing packet: dest={device_id[:8]}... "
            f"type={payload_type} size={len(packet_data)}B "
            f"from={source_satellite} rssi={rssi:.0f}dBm"
        )

        # Deliver to backend
        success = await self._deliver_to_backend(
            device_id=device_id,
            packet_data=packet_data,
            source_satellite=source_satellite,
            payload_type=payload_type,
            rssi=rssi,
            snr=snr,
        )

        routed = RoutedPacket(
            packet_hash=self._packet_hash(packet_data),
            source_satellite=source_satellite,
            destination_id=device_id,
            payload_type=payload_type,
            payload_size=len(packet_data),
            rssi=rssi,
            snr=snr,
            received_at=time.time(),
            delivered_at=time.time() if success else 0.0,
            delivery_status="delivered" if success else "failed",
        )
        self._routed_packets.append(routed)

        if success:
            self._stats["delivered"] += 1
        else:
            self._stats["delivery_failed"] += 1

        return success

    async def _deliver_to_backend(
        self,
        device_id: str,
        packet_data: bytes,
        source_satellite: str,
        payload_type: int,
        rssi: float,
        snr: float,
    ) -> bool:
        """Deliver a packet to the FastAPI backend inbox endpoint."""
        import base64

        url = f"{self.backend_url}/api/v1/inbox/deliver"
        payload = {
            "device_id": device_id,
            "packet_data": base64.b64encode(packet_data).decode("ascii"),
            "source_satellite": source_satellite,
            "payload_type": payload_type,
            "rssi": rssi,
            "snr": snr,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"Delivered to inbox: {device_id[:8]}...")
                    return True
                else:
                    logger.warning(f"Backend returned {resp.status}")
                    return False
        except urllib.error.HTTPError as e:
            logger.warning(f"Backend HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
            return False
        except Exception as e:
            logger.error(f"Backend delivery failed: {e}")
            return False

    async def poll_and_route(
        self,
        tinygs_client,
        satellite_filter: Optional[str] = None,
        interval_s: float = 60.0,
        max_iterations: int = 0,
    ) -> None:
        """
        Continuously poll TinyGS for new packets and route to inboxes.

        Args:
            tinygs_client: TinyGSClient instance
            satellite_filter: Only process packets from this satellite
            interval_s: Polling interval in seconds
            max_iterations: 0 = run forever
        """
        import base64

        iteration = 0
        logger.info(
            f"Starting inbox polling: interval={interval_s}s, "
            f"filter={satellite_filter or 'all'}"
        )

        while max_iterations == 0 or iteration < max_iterations:
            try:
                # Fetch recent packets from TinyGS
                packets = tinygs_client.receive_packets(
                    since_timestamp=time.time() - interval_s * 2,
                    limit=50,
                )

                for pkt in packets:
                    # Extract raw packet data
                    raw_b64 = pkt.get("data", pkt.get("frame", pkt.get("payload", "")))
                    if not raw_b64:
                        continue

                    try:
                        packet_data = base64.b64decode(raw_b64)
                    except Exception:
                        continue

                    # Filter by satellite
                    sat_name = pkt.get("satellite", pkt.get("sat", "unknown"))
                    if satellite_filter and satellite_filter.lower() not in sat_name.lower():
                        continue

                    rssi = float(pkt.get("rssi", pkt.get("RSSI", 0)))
                    snr = float(pkt.get("snr", pkt.get("SNR", 0)))

                    await self.route_packet(packet_data, sat_name, rssi, snr)

            except Exception as e:
                logger.error(f"Polling error: {e}")

            iteration += 1
            await asyncio.sleep(interval_s)

    def get_stats(self) -> dict:
        """Return routing statistics."""
        return {
            **self._stats,
            "dedup_cache_size": len(self._seen_hashes),
            "routed_history_size": len(self._routed_packets),
        }

    def recent_deliveries(self, limit: int = 20) -> list[dict]:
        """Return recent delivery records."""
        recent = self._routed_packets[-limit:]
        return [
            {
                "hash": r.packet_hash,
                "satellite": r.source_satellite,
                "destination": r.destination_id[:8] + "...",
                "type": r.payload_type,
                "size": r.payload_size,
                "rssi": r.rssi,
                "status": r.delivery_status,
                "age_s": round(time.time() - r.received_at, 0),
            }
            for r in reversed(recent)
        ]
