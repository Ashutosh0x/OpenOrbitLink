"""
OpenOrbitLink LoRa Hardware Driver -- SX1276/SX1262 via SPI

Provides a real LoRa transceiver interface for Raspberry Pi ground stations.
Uses the LoRaRF library for SPI communication with Semtech SX127x/SX126x chips.

Falls back to simulation mode if hardware is not detected, enabling development
and testing without physical RF hardware.

Hardware BOM:
  - Raspberry Pi Zero 2W (~INR 1,800)
  - RA-02 SX1276 module (~INR 600)
  - Quarter-wave wire antenna (~INR 200)
  Total: ~INR 2,600

Wiring (RA-02 -> RPi GPIO):
  VCC   -> 3.3V (pin 1)
  GND   -> GND  (pin 6)
  SCK   -> SPI0_SCLK (GPIO 11, pin 23)
  MISO  -> SPI0_MISO (GPIO  9, pin 21)
  MOSI  -> SPI0_MOSI (GPIO 10, pin 19)
  NSS   -> SPI0_CE0  (GPIO  8, pin 24) or any GPIO
  DIO0  -> GPIO 24   (pin 18) -- RX/TX done interrupt
  RST   -> GPIO 25   (pin 22) -- hardware reset

Usage:
    driver = SX1276Driver()
    await driver.init()
    result = await driver.transmit(b"Hello from OpenOrbitLink!")
    packet = await driver.receive(timeout_ms=5000)
    await driver.shutdown()
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

logger = logging.getLogger("OpenOrbitLink.LoRaDriver")

# Try to import LoRaRF for real hardware
try:
    from LoRaRF import SX1276, LoRaSPI, LoRaGPIO
    HAS_LORARF = True
except ImportError:
    HAS_LORARF = False

# Try RPi.GPIO as fallback for GPIO control
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False


class DriverMode(IntEnum):
    """Operating mode of the LoRa driver."""
    HARDWARE = 0      # Real SX1276 via SPI
    SIMULATION = 1    # Software simulation (no hardware)
    SERIAL_AT = 2     # AT-command serial module (RYLR896 etc)


class TxStatus(IntEnum):
    """Transmission result status."""
    SUCCESS = 0
    DUTY_CYCLE_EXCEEDED = 1
    TX_HARDWARE_ERROR = 2
    PASS_ENDED = 3
    NO_PACKETS = 4
    PAYLOAD_TOO_LARGE = 5
    NOT_INITIALIZED = 6


@dataclass
class TxResult:
    """Result of a single packet transmission."""
    status: TxStatus
    packet_size: int = 0
    airtime_ms: float = 0.0
    rssi: float = 0.0
    frequency_hz: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class RxPacket:
    """A received LoRa packet."""
    data: bytes
    rssi: float
    snr: float
    frequency_hz: float
    timestamp: float = field(default_factory=time.time)
    spreading_factor: int = 0
    bandwidth_hz: int = 0


@dataclass
class LoRaConfig:
    """LoRa radio configuration."""
    frequency_hz: int = 868_000_000
    spreading_factor: int = 12
    bandwidth_hz: int = 125_000
    coding_rate: int = 5          # 4/5
    tx_power_dbm: int = 14        # 100 mW (ISM limit EU)
    preamble_length: int = 8
    sync_word: int = 0x12         # LoRa private network
    max_payload: int = 80         # FOSSA frame size
    crc_enabled: bool = True
    implicit_header: bool = False
    low_data_rate_opt: bool = True  # Required for SF11/SF12 at BW125

    # Hardware pins (RPi GPIO BCM numbering)
    spi_bus: int = 0
    spi_cs: int = 0
    dio0_pin: int = 24
    reset_pin: int = 25


class SX1276Driver:
    """
    SX1276 LoRa transceiver driver.

    Supports real hardware via LoRaRF library, with automatic fallback
    to simulation mode if hardware is not detected.
    """

    def __init__(self, config: Optional[LoRaConfig] = None):
        self.config = config or LoRaConfig()
        self.mode = DriverMode.SIMULATION
        self._lora = None
        self._initialized = False
        self._current_frequency = self.config.frequency_hz
        self._last_rssi: float = 0.0
        self._last_snr: float = 0.0
        self._tx_count: int = 0
        self._rx_count: int = 0
        self._sim_rx_queue: list[bytes] = []

    async def init(self) -> bool:
        """
        Initialize the LoRa transceiver.

        Attempts hardware initialization first, falls back to simulation
        if hardware is not available.

        Returns:
            True if initialization succeeded
        """
        if HAS_LORARF:
            try:
                return await self._init_hardware()
            except Exception as e:
                logger.warning(f"Hardware init failed, falling back to simulation: {e}")

        logger.info("LoRa driver starting in SIMULATION mode (no hardware detected)")
        self.mode = DriverMode.SIMULATION
        self._initialized = True
        return True

    async def _init_hardware(self) -> bool:
        """Initialize real SX1276 hardware via SPI."""
        logger.info("Initializing SX1276 hardware...")

        self._lora = SX1276()

        # Configure SPI
        spi = LoRaSPI(self.config.spi_bus, self.config.spi_cs)

        # Configure GPIO pins
        gpio = LoRaGPIO(
            self.config.reset_pin,
            self.config.dio0_pin,
        )

        # Begin with SPI and GPIO
        if not self._lora.begin(spi, gpio):
            raise RuntimeError("SX1276 begin() failed -- check wiring and SPI")

        # Set frequency
        self._lora.setFrequency(self.config.frequency_hz)

        # Set spreading factor
        self._lora.setSpreadingFactor(self.config.spreading_factor)

        # Set bandwidth
        bw_map = {
            7_800: 0, 10_400: 1, 15_600: 2, 20_800: 3,
            31_250: 4, 41_700: 5, 62_500: 6, 125_000: 7,
            250_000: 8, 500_000: 9,
        }
        bw_idx = bw_map.get(self.config.bandwidth_hz, 7)
        self._lora.setBandwidth(bw_idx)

        # Set coding rate
        self._lora.setCodingRate(self.config.coding_rate)

        # Set TX power
        self._lora.setTxPower(self.config.tx_power_dbm)

        # Set preamble length
        self._lora.setPreambleLength(self.config.preamble_length)

        # Set sync word
        self._lora.setSyncWord(self.config.sync_word)

        # Enable CRC
        if self.config.crc_enabled:
            self._lora.setCrcEnable(True)

        # Header mode
        self._lora.setHeaderMode(1 if self.config.implicit_header else 0)

        # Low data rate optimization for SF11/SF12
        if self.config.low_data_rate_opt and self.config.spreading_factor >= 11:
            self._lora.setLdroEnable(True)

        self.mode = DriverMode.HARDWARE
        self._initialized = True
        self._current_frequency = self.config.frequency_hz

        logger.info(
            f"SX1276 initialized: "
            f"{self.config.frequency_hz/1e6:.3f} MHz, "
            f"SF{self.config.spreading_factor}, "
            f"BW{self.config.bandwidth_hz//1000}k, "
            f"TX {self.config.tx_power_dbm} dBm"
        )
        return True

    async def transmit(
        self,
        data: bytes,
        frequency_offset_hz: float = 0,
    ) -> TxResult:
        """
        Transmit a LoRa packet.

        Args:
            data: Packet payload (max 80 bytes)
            frequency_offset_hz: Doppler pre-compensation offset

        Returns:
            TxResult with status and metrics
        """
        if not self._initialized:
            return TxResult(status=TxStatus.NOT_INITIALIZED)

        if len(data) > self.config.max_payload:
            return TxResult(
                status=TxStatus.PAYLOAD_TOO_LARGE,
                packet_size=len(data),
            )

        # Apply frequency offset for Doppler compensation
        if frequency_offset_hz != 0:
            await self.set_frequency(
                self.config.frequency_hz + int(frequency_offset_hz)
            )

        start = time.time()

        if self.mode == DriverMode.HARDWARE:
            try:
                self._lora.beginPacket()
                self._lora.write(list(data))
                self._lora.endPacket()

                # Wait for TX done (blocking with timeout)
                await asyncio.sleep(0.01)  # Yield to event loop

                airtime_ms = (time.time() - start) * 1000
                self._tx_count += 1

                return TxResult(
                    status=TxStatus.SUCCESS,
                    packet_size=len(data),
                    airtime_ms=airtime_ms,
                    frequency_hz=self._current_frequency,
                )

            except Exception as e:
                logger.error(f"TX hardware error: {e}")
                return TxResult(
                    status=TxStatus.TX_HARDWARE_ERROR,
                    packet_size=len(data),
                )

        else:  # Simulation mode
            # Simulate realistic airtime
            airtime_ms = self._estimate_airtime_ms(len(data))
            await asyncio.sleep(airtime_ms / 1000.0)
            self._tx_count += 1

            logger.debug(
                f"SIM TX: {len(data)}B, "
                f"airtime={airtime_ms:.0f}ms, "
                f"doppler={frequency_offset_hz:+.0f}Hz"
            )

            return TxResult(
                status=TxStatus.SUCCESS,
                packet_size=len(data),
                airtime_ms=airtime_ms,
                frequency_hz=self._current_frequency,
            )

    async def receive(self, timeout_ms: int = 5000) -> Optional[RxPacket]:
        """
        Listen for an incoming LoRa packet.

        Args:
            timeout_ms: Maximum wait time in milliseconds

        Returns:
            RxPacket if received, None on timeout
        """
        if not self._initialized:
            return None

        if self.mode == DriverMode.HARDWARE:
            deadline = time.time() + timeout_ms / 1000.0

            # Put radio in RX mode
            self._lora.request()

            while time.time() < deadline:
                if self._lora.available():
                    # Read packet
                    length = self._lora.available()
                    data = bytes(self._lora.read(length))

                    self._last_rssi = self._lora.packetRssi()
                    self._last_snr = self._lora.snr()
                    self._rx_count += 1

                    return RxPacket(
                        data=data,
                        rssi=self._last_rssi,
                        snr=self._last_snr,
                        frequency_hz=self._current_frequency,
                        spreading_factor=self.config.spreading_factor,
                        bandwidth_hz=self.config.bandwidth_hz,
                    )

                await asyncio.sleep(0.01)

            return None

        else:  # Simulation mode
            if self._sim_rx_queue:
                data = self._sim_rx_queue.pop(0)
                self._rx_count += 1
                return RxPacket(
                    data=data,
                    rssi=-80.0,
                    snr=10.0,
                    frequency_hz=self._current_frequency,
                )

            await asyncio.sleep(min(timeout_ms / 1000.0, 0.5))
            return None

    async def set_frequency(self, frequency_hz: float) -> None:
        """Set the radio frequency (used for Doppler compensation)."""
        self._current_frequency = int(frequency_hz)
        if self.mode == DriverMode.HARDWARE and self._lora:
            self._lora.setFrequency(int(frequency_hz))

    async def shutdown(self) -> None:
        """Shut down the LoRa transceiver."""
        if self.mode == DriverMode.HARDWARE and self._lora:
            self._lora.sleep()
        self._initialized = False
        logger.info(
            f"LoRa driver shut down: TX={self._tx_count}, RX={self._rx_count}"
        )

    # -- Properties --

    @property
    def is_connected(self) -> bool:
        """Whether the driver is initialized and ready."""
        return self._initialized

    @property
    def rssi(self) -> float:
        """Last received packet RSSI (dBm)."""
        return self._last_rssi

    @property
    def snr(self) -> float:
        """Last received packet SNR (dB)."""
        return self._last_snr

    @property
    def is_hardware(self) -> bool:
        """True if using real RF hardware."""
        return self.mode == DriverMode.HARDWARE

    def get_status(self) -> dict:
        """Return driver status for monitoring."""
        return {
            "mode": self.mode.name,
            "initialized": self._initialized,
            "frequency_hz": self._current_frequency,
            "spreading_factor": self.config.spreading_factor,
            "bandwidth_hz": self.config.bandwidth_hz,
            "tx_power_dbm": self.config.tx_power_dbm,
            "tx_count": self._tx_count,
            "rx_count": self._rx_count,
            "last_rssi": self._last_rssi,
            "last_snr": self._last_snr,
        }

    # -- Simulation helpers --

    def inject_rx_packet(self, data: bytes) -> None:
        """Inject a packet into the simulation RX queue (for testing)."""
        if self.mode == DriverMode.SIMULATION:
            self._sim_rx_queue.append(data)

    def _estimate_airtime_ms(self, payload_bytes: int) -> float:
        """Estimate packet airtime using Semtech formulas."""
        sf = self.config.spreading_factor
        bw = self.config.bandwidth_hz

        t_sym = (2 ** sf) / bw * 1000  # ms per symbol

        # Preamble
        t_preamble = (self.config.preamble_length + 4.25) * t_sym

        # Payload symbols
        de = 1 if self.config.low_data_rate_opt and sf >= 11 else 0
        ih = 0 if not self.config.implicit_header else 1
        cr = self.config.coding_rate

        import math
        numerator = 8 * payload_bytes - 4 * sf + 28 + 16 - 20 * ih
        denominator = 4 * (sf - 2 * de)

        if denominator <= 0:
            n_payload = 8
        else:
            n_payload = 8 + max(0, math.ceil(numerator / denominator)) * cr

        t_payload = n_payload * t_sym
        return t_preamble + t_payload
