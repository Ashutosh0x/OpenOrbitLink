from __future__ import annotations
"""
OpenOrbitLink Ground Station Relay Daemon

Runs on Raspberry Pi + RTL-SDR to provide community relay node functionality.
Integrates with SatNOGS for satellite scheduling, GNU Radio for signal
processing, and the OpenOrbitLink DTN engine for store-and-forward relay.

Usage:
    python -m ground_station.relay_daemon --config config/ground_station.yaml
"""

import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("OpenOrbitLink.GroundStation")


@dataclass
class GroundStationConfig:
    """Configuration for a OpenOrbitLink ground station relay node."""
    station_id: str = "FS-GS-001"
    latitude: float = 28.6139        # New Delhi default
    longitude: float = 77.2090
    altitude_m: float = 216.0

    # SDR configuration
    sdr_device: str = "rtlsdr"       # rtlsdr or hackrf
    sdr_sample_rate: int = 2_400_000
    sdr_gain: float = 40.0

    # Frequencies to monitor (Hz)
    frequencies: list = field(default_factory=lambda: [
        144_390_000,   # ISS APRS
        145_800_000,   # ISS general
        137_100_000,   # NOAA-19
        137_912_500,   # NOAA-18
        145_935_000,   # FUNcube-1
    ])

    # Network
    api_port: int = 8080
    satnogs_enabled: bool = True
    lora_gateway: bool = True
    lora_frequency: int = 868_000_000

    # Storage
    db_path: str = "ground_station.db"
    observation_dir: str = "observations/"
    max_storage_gb: float = 10.0

    # DTN relay
    relay_enabled: bool = True
    max_relay_hops: int = 5


class SatNOGSIntegration:
    """Interface to SatNOGS network for satellite scheduling."""

    SATNOGS_API = "https://network.satnogs.org/api"
    SATNOGS_DB_API = "https://db.satnogs.org/api"

    def __init__(self, station_id: Optional[str] = None, api_token: Optional[str] = None):
        self.station_id = station_id
        self.api_token = api_token

    async def get_scheduled_observations(self) -> list[dict]:
        """Fetch scheduled observations from SatNOGS network."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {}
                if self.api_token:
                    headers["Authorization"] = f"Token {self.api_token}"

                url = f"{self.SATNOGS_API}/observations/"
                params = {"ground_station": self.station_id} if self.station_id else {}

                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.warning(f"SatNOGS API returned {resp.status}")
                        return []
        except ImportError:
            logger.warning("aiohttp not installed. SatNOGS integration disabled.")
            return []
        except Exception as e:
            logger.error(f"SatNOGS API error: {e}")
            return []

    async def get_satellite_info(self, norad_id: int) -> Optional[dict]:
        """Get satellite info from SatNOGS DB."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{self.SATNOGS_DB_API}/satellites/{norad_id}/"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"SatNOGS DB error: {e}")
        return None

    async def fetch_tle(self, norad_id: int) -> Optional[tuple[str, str]]:
        """Fetch latest TLE for a satellite."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{self.SATNOGS_DB_API}/tle/?sat_id={norad_id}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            tle = data[0]
                            return tle.get("tle1"), tle.get("tle2")
        except Exception as e:
            logger.error(f"TLE fetch error: {e}")
        return None


# Import real LoRa driver and pass scheduler
try:
    from .lora_driver import SX1276Driver, LoRaConfig
    HAS_LORA_DRIVER = True
except ImportError:
    HAS_LORA_DRIVER = False

try:
    from scripts.pass_scheduler import PassScheduler
    HAS_PASS_SCHEDULER = True
except ImportError:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.pass_scheduler import PassScheduler
        HAS_PASS_SCHEDULER = True
    except ImportError:
        HAS_PASS_SCHEDULER = False

try:
    from .doppler import DopplerCompensator
    HAS_DOPPLER = True
except ImportError:
    HAS_DOPPLER = False

try:
    from .pass_integration import PassTransmitter, DutyCycleTracker
    HAS_PASS_INTEGRATION = True
except ImportError:
    HAS_PASS_INTEGRATION = False

try:
    from .inbox_router import InboxRouter
    HAS_INBOX_ROUTER = True
except ImportError:
    HAS_INBOX_ROUTER = False


class GroundStationDaemon:
    """
    Main ground station relay daemon.

    Lifecycle:
    1. Initialize hardware (SDR, LoRa, GPS)
    2. Sync with SatNOGS for satellite schedule
    3. Main loop:
       a. Monitor LoRa mesh for incoming messages
       b. Wait for satellite pass windows
       c. Relay buffered messages during passes
       d. Receive and forward satellite data to mesh
    """

    def __init__(self, config: GroundStationConfig):
        self.config = config
        self.satnogs = SatNOGSIntegration()
        self._running = False
        self._relay_buffer: list[bytes] = []
        self._stats = {
            "packets_received": 0,
            "packets_relayed": 0,
            "satellite_passes": 0,
            "uptime_seconds": 0,
            "start_time": 0,
        }

        # Initialize LoRa driver (real or simulation)
        if HAS_LORA_DRIVER:
            lora_config = LoRaConfig(
                frequency_hz=config.lora_frequency,
                spreading_factor=12,
                tx_power_dbm=14,
            )
            self.lora = SX1276Driver(lora_config)
        else:
            self.lora = None

        # Initialize pass scheduler
        self.pass_scheduler = None
        if HAS_PASS_SCHEDULER:
            tle_path = str(Path(config.db_path).parent / "data" / "openorbitlink_satellites.tle")
            if Path(tle_path).exists():
                self.pass_scheduler = PassScheduler(
                    tle_path=tle_path,
                    observer_lat=config.latitude,
                    observer_lon=config.longitude,
                    observer_alt=config.altitude_m,
                )
            else:
                logger.warning(f"TLE file not found: {tle_path}. Pass prediction disabled.")

        # Initialize Doppler compensator
        self.doppler = None
        if HAS_DOPPLER and self.pass_scheduler:
            self.doppler = DopplerCompensator(
                self.pass_scheduler,
                carrier_freq_hz=config.lora_frequency,
            )

        # Initialize duty cycle tracker
        self.duty_cycle = DutyCycleTracker() if HAS_PASS_INTEGRATION else None

        # Initialize inbox router
        self.inbox_router = None
        if HAS_INBOX_ROUTER:
            self.inbox_router = InboxRouter(backend_url="http://localhost:8000")

    async def start(self):
        """Start the ground station daemon."""
        logger.info("=" * 60)
        logger.info(f"OpenOrbitLink Ground Station -- {self.config.station_id}")
        logger.info(f"Location: ({self.config.latitude:.4f}, {self.config.longitude:.4f})")
        logger.info(f"SDR: {self.config.sdr_device}")
        logger.info(f"LoRa: {'SX1276 driver' if self.lora else 'disabled'}")
        logger.info(f"Pass Scheduler: {'active' if self.pass_scheduler else 'disabled'}")
        logger.info(f"Doppler: {'active' if self.doppler else 'disabled'}")
        logger.info(f"Frequencies: {len(self.config.frequencies)} monitored")
        logger.info("=" * 60)

        self._running = True
        self._stats["start_time"] = time.time()

        # Initialize LoRa hardware
        if self.lora:
            await self.lora.init()

        # Start main loops
        tasks = [
            asyncio.create_task(self._satellite_pass_loop()),
            asyncio.create_task(self._lora_receive_loop()),
            asyncio.create_task(self._downlink_poll_loop()),
            asyncio.create_task(self._status_report_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Ground station shutting down...")
        finally:
            self._running = False
            if self.lora:
                await self.lora.shutdown()

    async def _lora_receive_loop(self):
        """Listen for incoming LoRa mesh packets."""
        if not self.lora:
            return
        while self._running:
            packet = await self.lora.receive(timeout_ms=1000)
            if packet:
                self._stats["packets_received"] += 1
                self._relay_buffer.append(packet.data)
                logger.info(
                    f"LoRa RX: {len(packet.data)} bytes "
                    f"RSSI={packet.rssi:.0f}dBm SNR={packet.snr:.1f}dB "
                    f"(buffer: {len(self._relay_buffer)})"
                )
            await asyncio.sleep(0.05)

    async def _satellite_pass_loop(self):
        """Monitor satellite passes and burst-transmit during windows."""
        if not self.pass_scheduler:
            logger.info("Pass scheduler not available, falling back to SatNOGS polling")
            while self._running:
                if self.config.satnogs_enabled:
                    observations = await self.satnogs.get_scheduled_observations()
                    if observations:
                        logger.info(f"Next {len(observations)} SatNOGS observations scheduled")
                await asyncio.sleep(60)
            return

        target_sats = ["FOSSASAT", "ISS"]

        while self._running:
            for sat_name in target_sats:
                should_tx, current_pass = self.pass_scheduler.should_transmit_now(sat_name)

                if should_tx and current_pass and self._relay_buffer:
                    logger.info(
                        f"** SATELLITE PASS: {current_pass.satellite_name} "
                        f"El={current_pass.max_elevation_deg:.1f}d "
                        f"Duration={current_pass.duration_s:.0f}s **"
                    )
                    self._stats["satellite_passes"] += 1

                    # Burst transmit during pass
                    await self._burst_transmit(
                        current_pass.satellite_name,
                        current_pass.duration_s,
                    )

            # Report next pass ETA
            for sat_name in target_sats:
                eta = self.pass_scheduler.time_to_next_pass(sat_name)
                if eta is not None and eta > 0:
                    logger.debug(f"Next {sat_name} pass in {eta/60:.0f} min")

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _burst_transmit(self, satellite_name: str, duration_s: float):
        """Burst-transmit buffered packets during a satellite pass."""
        if not self.lora or not self._relay_buffer:
            return

        start = time.time()
        sent = 0
        failed = 0

        while self._relay_buffer and (time.time() - start) < duration_s:
            data = self._relay_buffer[0]

            # Compute Doppler offset
            freq_offset = 0.0
            if self.doppler:
                freq_offset = self.doppler.frequency_offset_at(satellite_name)

            # Check duty cycle
            if self.duty_cycle and not self.duty_cycle.can_transmit(2.0):  # ~2s per packet
                logger.warning("Duty cycle budget exhausted")
                break

            result = await self.lora.transmit(data[:80], freq_offset)
            if hasattr(result, 'status') and result.status == 0:  # SUCCESS
                self._relay_buffer.pop(0)
                sent += 1
                self._stats["packets_relayed"] += 1
                if self.duty_cycle:
                    self.duty_cycle.record_tx(result.airtime_ms / 1000.0)
            else:
                failed += 1
                self._relay_buffer.pop(0)  # Drop failed packet after attempt

            await asyncio.sleep(0.2)  # Inter-packet gap

        logger.info(f"Burst TX complete: sent={sent} failed={failed} remaining={len(self._relay_buffer)}")

    async def _downlink_poll_loop(self):
        """Poll for satellite downlink packets and route to inboxes."""
        if not self.inbox_router:
            return

        from .tinygs_client import TinyGSClient
        tinygs = TinyGSClient()

        while self._running:
            try:
                # Adaptive polling: faster during passes, slower between
                is_pass = False
                if self.pass_scheduler:
                    for sat in ["FOSSASAT", "ISS"]:
                        should_tx, _ = self.pass_scheduler.should_transmit_now(sat)
                        if should_tx:
                            is_pass = True
                            break

                interval = 30.0 if is_pass else 300.0

                packets = tinygs.receive_packets(
                    since_timestamp=time.time() - interval * 2,
                    limit=20,
                )

                for pkt in packets:
                    import base64
                    raw_b64 = pkt.get("data", pkt.get("frame", ""))
                    if raw_b64:
                        try:
                            packet_data = base64.b64decode(raw_b64)
                            sat_name = pkt.get("satellite", "unknown")
                            rssi = float(pkt.get("rssi", 0))
                            snr = float(pkt.get("snr", 0))
                            await self.inbox_router.route_packet(
                                packet_data, sat_name, rssi, snr
                            )
                        except Exception:
                            pass

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Downlink poll error: {e}")
                await asyncio.sleep(60)

    async def _status_report_loop(self):
        """Periodic status reporting."""
        while self._running:
            uptime = time.time() - self._stats["start_time"]
            self._stats["uptime_seconds"] = uptime

            logger.info(
                f"Status | Uptime: {uptime/3600:.1f}h | "
                f"RX: {self._stats['packets_received']} | "
                f"Relayed: {self._stats['packets_relayed']} | "
                f"API-injected: {self._stats.get('api_injected', 0)} | "
                f"Buffer: {len(self._relay_buffer)} | "
                f"Passes: {self._stats['satellite_passes']}"
            )
            await asyncio.sleep(300)  # Every 5 minutes

    # ─── API Integration Methods ────────────────────────────────────────

    def get_daemon_status(self) -> dict:
        """Return daemon status for the FastAPI backend."""
        uptime = time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
        return {
            "station_id": self.config.station_id,
            "latitude": self.config.latitude,
            "longitude": self.config.longitude,
            "altitude_m": self.config.altitude_m,
            "sdr_device": self.config.sdr_device,
            "lora_frequency_hz": self.config.lora_frequency,
            "lora_gateway_active": self.config.lora_gateway and self.lora._connected,
            "satnogs_enabled": self.config.satnogs_enabled,
            "relay_enabled": self.config.relay_enabled,
            "running": self._running,
            "uptime_seconds": uptime,
            "packets_received": self._stats["packets_received"],
            "packets_relayed": self._stats["packets_relayed"],
            "api_injected": self._stats.get("api_injected", 0),
            "relay_buffer_size": len(self._relay_buffer),
            "satellite_passes": self._stats["satellite_passes"],
        }

    def submit_to_relay_buffer(self, data: bytes, user_id: str = "api") -> dict:
        """
        Inject a message into the relay buffer from the FastAPI backend.

        Called by backend.tx_queue when a user sends a message via the API.
        The message will be transmitted during the next satellite pass or
        LoRa mesh window.
        """
        self._relay_buffer.append(data)
        self._stats["api_injected"] = self._stats.get("api_injected", 0) + 1
        logger.info(
            f"API inject: {len(data)} bytes from user '{user_id}' "
            f"(buffer: {len(self._relay_buffer)})"
        )
        return {
            "accepted": True,
            "buffer_position": len(self._relay_buffer),
            "buffer_size": len(self._relay_buffer),
            "user_id": user_id,
        }

    def get_relay_buffer_status(self) -> dict:
        """Return the current relay buffer status for queue monitoring."""
        return {
            "buffer_size": len(self._relay_buffer),
            "max_relay_hops": self.config.max_relay_hops,
            "relay_enabled": self.config.relay_enabled,
        }



def main():
    import argparse

    parser = argparse.ArgumentParser(description="OpenOrbitLink Ground Station Relay Daemon")
    parser.add_argument("--station-id", default="FS-GS-001")
    parser.add_argument("--lat", type=float, default=28.6139)
    parser.add_argument("--lon", type=float, default=77.2090)
    parser.add_argument("--alt", type=float, default=216.0)
    parser.add_argument("--sdr", default="rtlsdr", choices=["rtlsdr", "hackrf"])
    parser.add_argument("--no-satnogs", action="store_true")
    parser.add_argument("--no-lora", action="store_true")
    args = parser.parse_args()

    config = GroundStationConfig(
        station_id=args.station_id,
        latitude=args.lat,
        longitude=args.lon,
        altitude_m=args.alt,
        sdr_device=args.sdr,
        satnogs_enabled=not args.no_satnogs,
        lora_gateway=not args.no_lora,
    )

    daemon = GroundStationDaemon(config)

    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")


if __name__ == "__main__":
    main()

