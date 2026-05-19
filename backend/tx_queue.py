"""
OpenOrbitLink Transmission Queue.

Bridges the FastAPI backend to the existing DTN engine and ground station
infrastructure. Manages the lifecycle of messages from API submission
through duty-cycle gating to LoRa transmission.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import (
    Message,
    MessageDirection,
    MessageStatus,
    TxLog,
    async_session,
)
from .rate_limiter import duty_cycle_tracker

logger = logging.getLogger("OpenOrbitLink.TxQueue")


class TransmitQueue:
    """
    Server-side message queue that bridges user API requests to the
    ground station LoRa transmitter.

    Lifecycle:
    1. User POSTs to /send → message inserted as QUEUED
    2. Background worker polls for QUEUED messages
    3. Checks duty cycle budget
    4. Creates DTN bundle via existing protocol stack
    5. Transmits via TinyGS client (or LoRa gateway)
    6. Logs transmission for regulatory compliance
    7. Updates message status
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_count = 0
        self._error_count = 0
        self._last_tx_time: Optional[float] = None

    async def start(self):
        """Start the background transmission worker."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("TX queue worker started")

    async def stop(self):
        """Gracefully stop the transmission worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TX queue worker stopped")

    async def _worker_loop(self):
        """Main worker loop: poll → check duty cycle → transmit."""
        while self._running:
            try:
                await self._process_pending()
            except Exception as e:
                logger.error(f"TX worker error: {e}")
                self._error_count += 1
            await asyncio.sleep(5.0)  # Poll every 5 seconds

    async def _process_pending(self):
        """Process pending messages from the queue."""
        async with async_session() as session:
            # Fetch oldest QUEUED messages, ordered by priority
            result = await session.execute(
                select(Message)
                .where(Message.status == MessageStatus.QUEUED)
                .where(Message.direction == MessageDirection.OUTBOUND)
                .order_by(Message.created_at.asc())
                .limit(10)
            )
            messages = result.scalars().all()

            for msg in messages:
                await self._transmit_message(msg, session)

    async def _transmit_message(self, msg: Message, session: AsyncSession):
        """Attempt to transmit a single message through the LoRa node."""
        # Estimate TX duration: payload bytes * 8 / 700 bps
        payload_bytes = len(msg.payload_text.encode("utf-8"))
        overhead_bytes = 21 + 32 + 2  # header + FEC + CRC
        total_bytes = payload_bytes + overhead_bytes
        estimated_duration = (total_bytes * 8) / 700.0

        # Check duty cycle budget
        if not duty_cycle_tracker.can_transmit(msg.user_id, estimated_duration):
            budget = duty_cycle_tracker.get_budget(msg.user_id)
            logger.info(
                f"Duty cycle limit: user {msg.user_id} has "
                f"{budget.remaining_seconds:.1f}s remaining, "
                f"need {estimated_duration:.1f}s. Deferring."
            )
            return

        # Mark as transmitting
        msg.status = MessageStatus.TRANSMITTING
        session.add(msg)
        await session.commit()

        try:
            # Create DTN bundle using existing protocol stack
            bundle_id = await self._create_and_transmit_bundle(
                msg.payload_text,
                msg.destination_address,
                msg.band.value if msg.band else "ism",
                msg.encrypted,
            )

            # Record successful transmission
            tx_time = time.time()
            duty_cycle_tracker.record_transmission(msg.user_id, estimated_duration)

            # Log for regulatory compliance
            tx_log = TxLog(
                user_id=msg.user_id,
                message_id=msg.id,
                tx_duration_seconds=estimated_duration,
                frequency_hz=settings.LORA_FREQUENCY_HZ,
                duty_cycle_remaining_seconds=duty_cycle_tracker.get_budget(
                    msg.user_id
                ).remaining_seconds,
            )
            session.add(tx_log)

            # Update message status
            msg.status = MessageStatus.AWAITING_ACK
            msg.bundle_id = bundle_id
            msg.transmitted_at = datetime.now(timezone.utc)
            session.add(msg)
            await session.commit()

            self._processed_count += 1
            self._last_tx_time = tx_time
            logger.info(
                f"TX success: msg {msg.id} → bundle {bundle_id} "
                f"({estimated_duration:.2f}s airtime)"
            )

        except Exception as e:
            logger.error(f"TX failed for msg {msg.id}: {e}")
            msg.status = MessageStatus.FAILED
            session.add(msg)
            await session.commit()
            self._error_count += 1

    async def _create_and_transmit_bundle(
        self,
        payload_text: str,
        destination: str,
        band: str,
        encrypted: bool,
    ) -> str:
        """
        Create a DTN bundle using the existing protocol stack and
        queue it for transmission.

        In simulation mode (no hardware), this creates the bundle
        and marks it as transmitted. With hardware, it would hand
        off to TinyGSClient or LoRaGateway.
        """
        import sys
        import os

        # Add project root to path for protocol imports
        project_root = str(Path(__file__).parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from protocol.packet import OpenOrbitLinkProtocol, TransmitBand
        from protocol.dtn import DTNEngine

        # Map band string to TransmitBand enum
        band_map = {
            "ism": TransmitBand.ISM,
            "amateur": TransmitBand.AMATEUR,
        }
        tx_band = band_map.get(band, TransmitBand.ISM)

        # Create protocol instance and bundle
        proto = OpenOrbitLinkProtocol(f"api-{settings.STATION_ID}")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "tx_bundles.db")
            dtn = DTNEngine(proto, db_path=db_path)
            bundle_id = dtn.queue_text(
                payload_text,
                destination=destination,
                band=tx_band,
                encrypt=encrypted,
            )

        # In production: hand off to TinyGSClient.transmit_frame()
        # For now: simulation mode — bundle created successfully
        logger.info(f"Bundle {bundle_id} created for destination '{destination}'")

        return bundle_id

    def get_stats(self) -> dict:
        """Get queue worker statistics."""
        return {
            "running": self._running,
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "last_tx_time": self._last_tx_time,
            "duty_cycle": duty_cycle_tracker.get_global_status(),
        }


# ─── Singleton ──────────────────────────────────────────────────────────

tx_queue = TransmitQueue()
