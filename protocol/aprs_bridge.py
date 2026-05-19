"""
OpenOrbitLink APRS-IS Bridge -- Internet Gateway for ISS APRS Fallback

When the ISS APRS digipeater (RS0ISS) is not overhead or when internet
is available, this bridge gates APRS packets through the APRS-IS internet
network (rotate.aprs.net:14580) for instant delivery.

Capabilities:
  - Send APRS position reports
  - Send APRS messages (with ack)
  - Receive APRS messages for our callsign
  - Callsign validation (ITU format)
  - Passcode computation (APRS-IS auth)
  - Fallback path when satellite ISS APRS is unavailable

Requirements:
  - Valid amateur radio callsign
  - pip install aprslib (optional, falls back to raw socket)

ISS APRS Details:
  - Uplink/Downlink: 145.825 MHz
  - Protocol: AX.25 1200 bps AFSK
  - Digipeater callsign: RS0ISS
  - ~6-8 passes/day over India
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("OpenOrbitLink.APRSBridge")

try:
    import aprslib
    HAS_APRSLIB = True
except ImportError:
    HAS_APRSLIB = False

# ITU callsign pattern: 1-2 letter prefix + digit + 1-3 letter suffix + optional SSID
CALLSIGN_PATTERN = re.compile(
    r'^[A-Z]{1,2}[0-9][A-Z]{1,3}(-(?:1[0-5]|[0-9]))?$',
    re.IGNORECASE,
)

# APRS-IS servers
APRS_IS_SERVERS = [
    "rotate.aprs.net",
    "euro.aprs2.net",
    "asia.aprs2.net",
    "noam.aprs2.net",
]


@dataclass
class APRSMessage:
    """An APRS message for send/receive."""
    source: str
    destination: str
    message: str
    message_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


class APRSBridge:
    """
    APRS-IS internet bridge for ISS APRS fallback path.

    Provides a TCP connection to the APRS-IS network for sending
    and receiving APRS packets when RF ISS digipeater is not available.
    """

    def __init__(
        self,
        callsign: str,
        passcode: Optional[str] = None,
        server: str = "rotate.aprs.net",
        port: int = 14580,
        aprs_filter: str = "",
    ):
        if not self.validate_callsign(callsign):
            raise ValueError(f"Invalid callsign format: {callsign}")

        self.callsign = callsign.upper()
        self.passcode = passcode or str(self.compute_passcode(self.callsign))
        self.server = server
        self.port = port
        self.aprs_filter = aprs_filter or f"b/{self.callsign}"

        self._connected = False
        self._socket: Optional[socket.socket] = None
        self._ais = None  # aprslib IS object
        self._rx_callback: Optional[Callable] = None
        self._sent_messages: list[APRSMessage] = []
        self._received_messages: list[APRSMessage] = []
        self._pending_acks: dict[str, APRSMessage] = {}

    @staticmethod
    def validate_callsign(callsign: str) -> bool:
        """
        Validate an amateur radio callsign against ITU format.

        Valid examples: VU2ABC, W1AW, JA1YRL, G3XYZ, VU3CWG-9
        Invalid: 123, ABCDEF, A1, VU2ABC-16
        """
        return bool(CALLSIGN_PATTERN.match(callsign.strip()))

    @staticmethod
    def compute_passcode(callsign: str) -> int:
        """
        Compute APRS-IS passcode for a callsign.

        The algorithm is a simple hash of the callsign (without SSID):
          hash = 0x73e2
          for each pair of characters: hash ^= (char1 << 8) | char2
        """
        # Strip SSID
        call = callsign.upper().split("-")[0]

        passcode = 0x73e2
        for i in range(0, len(call), 2):
            passcode ^= ord(call[i]) << 8
            if i + 1 < len(call):
                passcode ^= ord(call[i + 1])

        return passcode & 0x7FFF

    async def connect(self) -> bool:
        """
        Connect to APRS-IS server.

        Returns:
            True if connection and authentication succeeded
        """
        if HAS_APRSLIB:
            return await self._connect_aprslib()
        return await self._connect_raw()

    async def _connect_aprslib(self) -> bool:
        """Connect using aprslib library."""
        try:
            self._ais = aprslib.IS(
                self.callsign,
                passwd=self.passcode,
                host=self.server,
                port=self.port,
            )
            self._ais.connect()
            self._connected = True
            logger.info(f"Connected to APRS-IS via aprslib: {self.server}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"aprslib connection failed: {e}")
            return False

    async def _connect_raw(self) -> bool:
        """Connect using raw TCP socket (fallback)."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(30)
            self._socket.connect((self.server, self.port))

            # Read server banner
            banner = self._socket.recv(1024).decode("ascii", errors="replace")
            logger.debug(f"APRS-IS banner: {banner.strip()}")

            # Authenticate
            login_str = (
                f"user {self.callsign} pass {self.passcode} "
                f"vers OpenOrbitLink 1.0 filter {self.aprs_filter}\r\n"
            )
            self._socket.sendall(login_str.encode("ascii"))

            # Read login response
            response = self._socket.recv(1024).decode("ascii", errors="replace")
            if "verified" in response.lower() or "unverified" in response.lower():
                self._connected = True
                logger.info(f"Connected to APRS-IS (raw): {self.server}:{self.port}")
                return True
            else:
                logger.warning(f"APRS-IS auth response: {response.strip()}")
                return False

        except Exception as e:
            logger.error(f"Raw socket connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from APRS-IS."""
        if self._ais:
            try:
                self._ais.close()
            except Exception:
                pass
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self._connected = False
        logger.info("Disconnected from APRS-IS")

    async def send_position(
        self,
        lat: float,
        lon: float,
        comment: str = "OpenOrbitLink Ground Station",
        symbol: str = "/-",
    ) -> bool:
        """
        Send an APRS position report.

        Args:
            lat: Latitude in decimal degrees (positive = North)
            lon: Longitude in decimal degrees (positive = East)
            comment: Position comment string
            symbol: APRS symbol table/code (default: house)
        """
        if not self._connected:
            return False

        # Convert to APRS format: DDMM.MMN/DDDMM.MME
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        lat = abs(lat)
        lon = abs(lon)

        lat_deg = int(lat)
        lat_min = (lat - lat_deg) * 60
        lon_deg = int(lon)
        lon_min = (lon - lon_deg) * 60

        lat_str = f"{lat_deg:02d}{lat_min:05.2f}{lat_dir}"
        lon_str = f"{lon_deg:03d}{lon_min:05.2f}{lon_dir}"

        sym_table = symbol[0] if len(symbol) >= 1 else "/"
        sym_code = symbol[1] if len(symbol) >= 2 else "-"

        packet = f"{self.callsign}>APRS,TCPIP*:={lat_str}{sym_table}{lon_str}{sym_code}{comment}"
        return await self._send_raw(packet)

    async def send_message(
        self,
        destination: str,
        message: str,
        with_ack: bool = True,
    ) -> bool:
        """
        Send an APRS message to another station.

        Args:
            destination: Destination callsign (with optional SSID)
            message: Message text (max 67 chars for APRS)
            with_ack: Request acknowledgement
        """
        if not self._connected:
            return False

        # Pad destination to 9 chars
        dest_padded = destination.ljust(9)[:9]
        msg_id = ""

        if with_ack:
            msg_id = f"{{{int(time.time()) % 100000}"

        packet = f"{self.callsign}>APRS,TCPIP*::{dest_padded}:{message[:67]}{msg_id}"

        msg = APRSMessage(
            source=self.callsign,
            destination=destination,
            message=message,
            message_id=msg_id.strip("{") if msg_id else None,
        )
        self._sent_messages.append(msg)

        if msg_id:
            self._pending_acks[msg.message_id] = msg

        return await self._send_raw(packet)

    async def _send_raw(self, packet: str) -> bool:
        """Send a raw APRS packet string."""
        try:
            if self._ais:
                self._ais.sendall(packet)
                logger.info(f"APRS TX: {packet}")
                return True
            elif self._socket:
                self._socket.sendall(f"{packet}\r\n".encode("ascii"))
                logger.info(f"APRS TX: {packet}")
                return True
            return False
        except Exception as e:
            logger.error(f"APRS send failed: {e}")
            self._connected = False
            return False

    async def receive_messages(
        self,
        callback: Callable[[APRSMessage], None],
        timeout_s: float = 0,
    ) -> None:
        """
        Listen for incoming APRS messages.

        Args:
            callback: Function called for each received message
            timeout_s: 0 = run forever
        """
        self._rx_callback = callback
        start = time.time()

        if self._ais and HAS_APRSLIB:
            # Use aprslib consumer
            def _consumer(packet):
                try:
                    parsed = aprslib.parse(packet)
                    if parsed.get("format") == "message":
                        msg = APRSMessage(
                            source=parsed.get("from", ""),
                            destination=parsed.get("addresse", ""),
                            message=parsed.get("message_text", ""),
                            message_id=parsed.get("msgNo"),
                        )
                        self._received_messages.append(msg)
                        callback(msg)
                except Exception:
                    pass

            try:
                if timeout_s > 0:
                    # aprslib doesn't support timeout directly; use blocking=False
                    self._ais.consumer(_consumer, raw=False, blocking=True)
                else:
                    self._ais.consumer(_consumer, raw=False, blocking=True)
            except Exception as e:
                logger.error(f"APRS consumer error: {e}")

        elif self._socket:
            self._socket.settimeout(1.0)
            while True:
                if timeout_s > 0 and (time.time() - start) > timeout_s:
                    break
                try:
                    data = self._socket.recv(4096).decode("ascii", errors="replace")
                    for line in data.strip().split("\n"):
                        if line.startswith("#"):
                            continue
                        self._parse_message(line.strip(), callback)
                except socket.timeout:
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"APRS receive error: {e}")
                    break

    def _parse_message(self, raw: str, callback: Callable) -> None:
        """Parse a raw APRS packet for messages addressed to us."""
        try:
            # Basic format: SOURCE>DEST,PATH::ADDRESSEE :MESSAGE{MSGID
            if "::" not in raw:
                return

            header, body = raw.split("::", 1)
            source = header.split(">")[0]
            addressee = body[:9].strip()
            message_part = body[10:]

            # Check if addressed to us
            if addressee.upper() != self.callsign.upper():
                return

            # Extract message ID
            msg_id = None
            if "{" in message_part:
                message_text, msg_id = message_part.rsplit("{", 1)
                msg_id = msg_id.strip()
            else:
                message_text = message_part

            msg = APRSMessage(
                source=source,
                destination=addressee,
                message=message_text.strip(),
                message_id=msg_id,
            )

            # Handle ACK
            if message_text.strip().startswith("ack"):
                ack_id = message_text.strip()[3:]
                if ack_id in self._pending_acks:
                    self._pending_acks[ack_id].acknowledged = True
                    del self._pending_acks[ack_id]
                    logger.info(f"ACK received for message {ack_id}")
                return

            self._received_messages.append(msg)
            callback(msg)

            # Send ACK if requested
            if msg_id:
                asyncio.create_task(self._send_ack(source, msg_id))

        except Exception as e:
            logger.debug(f"APRS parse error: {e}")

    async def _send_ack(self, destination: str, msg_id: str) -> None:
        """Send an acknowledgement for a received message."""
        dest_padded = destination.ljust(9)[:9]
        ack_packet = f"{self.callsign}>APRS,TCPIP*::{dest_padded}:ack{msg_id}"
        await self._send_raw(ack_packet)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_stats(self) -> dict:
        return {
            "callsign": self.callsign,
            "server": self.server,
            "connected": self._connected,
            "sent": len(self._sent_messages),
            "received": len(self._received_messages),
            "pending_acks": len(self._pending_acks),
        }
