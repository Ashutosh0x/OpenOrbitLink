#!/usr/bin/env python3
"""
OpenOrbitLink Ground Station gRPC Server
===================================
Runs on Raspberry Pi to provide real-time telemetry, packet decoding,
and antenna control to the OpenOrbitLink Android app.

Inspired by Starlink's SXGrpc native module architecture — but open-source.

Usage:
    python grpc_server.py --port 50051 --station-id FS-GS-001
"""

import asyncio
import time
import math
import random
import logging
import argparse
from dataclasses import dataclass
from typing import List, Optional

import grpc
from ground_station import freesat_pb2, freesat_pb2_grpc

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger('OpenOrbitLink-GS')

# ─── Simulated Hardware Interface ───────────────────────────────────────

@dataclass
class StationConfig:
    station_id: str = "FS-GS-001"
    latitude: float = 28.6139     # New Delhi
    longitude: float = 77.2090
    altitude_m: float = 216.0
    hardware: str = "RPi 4B + RTL-SDR V4 + Yagi 144MHz"

@dataclass 
class AntennaState:
    azimuth: float = 0.0
    elevation: float = 45.0
    tracking_mode: str = "MANUAL"
    target_norad: int = 0

@dataclass
class ReceiverState:
    frequency_mhz: float = 145.800
    bandwidth_khz: float = 25.0
    modulation: str = "AFSK"
    gain_db: float = 40.0
    agc_enabled: bool = True
    ppm_correction: float = 0.5

@dataclass
class TelemetrySnapshot:
    signal_dbm: float = -98.0
    noise_floor_dbm: float = -120.0
    snr_db: float = 22.0
    doppler_khz: float = 0.0
    ber: float = 0.0003
    fec_corrections: int = 2
    packets_received: int = 0
    packets_errors: int = 0
    temperature_c: float = 42.0
    timestamp_ms: int = 0


class GroundStationService:
    """Core ground station service handling hardware and telemetry."""
    
    def __init__(self, config: StationConfig):
        self.config = config
        self.antenna = AntennaState()
        self.receiver = ReceiverState()
        self.telemetry = TelemetrySnapshot()
        self.start_time = time.time()
        self.total_packets = 0
        self._packet_log: List[dict] = []
        self._telemetry_history: List[dict] = []
        logger.info(f"Ground station {config.station_id} initialized")
        logger.info(f"Location: {config.latitude:.4f}, {config.longitude:.4f}")
        logger.info(f"Hardware: {config.hardware}")
    
    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)
    
    def update_telemetry(self):
        """Simulate telemetry updates from SDR hardware."""
        t = time.time()
        # Simulate varying signal conditions
        self.telemetry.signal_dbm = -98 + 10 * math.sin(t * 0.1) + random.gauss(0, 2)
        self.telemetry.noise_floor_dbm = -120 + random.gauss(0, 1)
        self.telemetry.snr_db = self.telemetry.signal_dbm - self.telemetry.noise_floor_dbm
        self.telemetry.doppler_khz = 4.5 * math.sin(t * 0.05)
        self.telemetry.ber = max(0.0001, 0.001 - 0.0005 * math.sin(t * 0.1))
        self.telemetry.fec_corrections = random.randint(0, 5)
        self.telemetry.temperature_c = 40 + 5 * math.sin(t * 0.01) + random.gauss(0, 0.5)
        self.telemetry.timestamp_ms = int(t * 1000)
        
        # Store history
        self._telemetry_history.append({
            'timestamp_ms': self.telemetry.timestamp_ms,
            'snr_db': round(self.telemetry.snr_db, 2),
            'signal_dbm': round(self.telemetry.signal_dbm, 2),
            'doppler_khz': round(self.telemetry.doppler_khz, 3),
        })
        # Keep last 60 seconds
        if len(self._telemetry_history) > 60:
            self._telemetry_history = self._telemetry_history[-60:]
    
    def generate_packet(self) -> Optional[dict]:
        """Simulate random packet reception."""
        if random.random() > 0.3:  # 30% chance per second
            return None
        
        self.total_packets += 1
        packet_types = [
            ("APRS", "RS0ISS", "CQ", "ISS", 25544, "Hello from ISS! Grid: FM18lv"),
            ("BEACON", "FS-GS-001", "ALL", "LOCAL", 0, f"Station alive | pkts={self.total_packets}"),
            ("AX25", "NOAA19", "WX", "NOAA-19", 33591, f"APT frame {random.randint(1000,9999)}"),
            ("OpenOrbitLink", "FS-USR-42", "FS-USR-17", "ISS", 25544, "Test message via satellite"),
            ("CCSDS", "METEOR", "GND", "METEOR-M2", 40069, f"LRPT data block {random.randint(100,999)}"),
        ]
        
        ptype, src, dst, sat, norad, text = random.choice(packet_types)
        crc_valid = random.random() > 0.05  # 95% CRC pass rate
        
        if not crc_valid:
            self.telemetry.packets_errors += 1
        else:
            self.telemetry.packets_received += 1
        
        packet = {
            'timestamp_ms': int(time.time() * 1000),
            'source': src,
            'destination': dst,
            'satellite': sat,
            'norad_id': norad,
            'frequency_mhz': self.receiver.frequency_mhz,
            'snr_db': round(self.telemetry.snr_db, 2),
            'decoded_text': text,
            'packet_type': ptype,
            'crc_valid': crc_valid,
        }
        
        self._packet_log.append(packet)
        if len(self._packet_log) > 100:
            self._packet_log = self._packet_log[-100:]
        
        logger.info(f"[{ptype}] {src}>{dst} via {sat}: {text}")
        return packet
    
    def generate_waterfall_frame(self) -> dict:
        """Simulate FFT waterfall data."""
        t = time.time()
        fft_size = 512
        spectrum = []
        for i in range(fft_size):
            freq_offset = (i - fft_size / 2) / fft_size * 25  # kHz
            # Noise floor + signal peaks
            power = -120 + random.gauss(0, 3)
            # Add a signal at center
            if abs(freq_offset) < 2:
                power += 30 * math.exp(-freq_offset**2 / 0.5)
            # Add a second signal offset
            if abs(freq_offset - 8) < 1.5:
                power += 20 * math.exp(-(freq_offset - 8)**2 / 0.3)
            spectrum.append(round(power, 1))
        
        return {
            'timestamp_ms': int(t * 1000),
            'center_frequency_mhz': self.receiver.frequency_mhz,
            'bandwidth_khz': self.receiver.bandwidth_khz,
            'power_spectrum_db': spectrum,
        }
    
    def set_antenna(self, azimuth: float, elevation: float, mode: str = "MANUAL",
                    target_norad: int = 0) -> dict:
        """Control antenna position."""
        self.antenna.azimuth = max(0, min(360, azimuth))
        self.antenna.elevation = max(0, min(90, elevation))
        self.antenna.tracking_mode = mode
        self.antenna.target_norad = target_norad
        logger.info(f"Antenna -> AZ {self.antenna.azimuth:.1f} EL {self.antenna.elevation:.1f} [{mode}]")
        return {
            'success': True,
            'current_azimuth': self.antenna.azimuth,
            'current_elevation': self.antenna.elevation,
            'active_mode': mode,
        }
    
    def set_frequency(self, freq_mhz: float, bandwidth_khz: float = 25.0,
                      modulation: str = "AFSK", gain_db: float = 40.0,
                      agc: bool = True) -> dict:
        """Set receiver frequency."""
        self.receiver.frequency_mhz = freq_mhz
        self.receiver.bandwidth_khz = bandwidth_khz
        self.receiver.modulation = modulation
        self.receiver.gain_db = gain_db
        self.receiver.agc_enabled = agc
        logger.info(f"Tuned to {freq_mhz:.3f} MHz | BW {bandwidth_khz} kHz | {modulation}")
        return {
            'success': True,
            'actual_frequency_mhz': freq_mhz,
            'ppm_correction': self.receiver.ppm_correction,
        }
    
    def run_speed_test(self, packet_count: int = 100, packet_size: int = 256) -> dict:
        """Simulate satellite link speed test."""
        # Simulated results for satellite link
        return {
            'upload_bps': 700.0,      # Codec2 rate
            'download_bps': 1200.0,   # BPSK 1200 baud
            'avg_latency_ms': 890.0,  # LEO satellite
            'jitter_ms': 45.0,
            'packet_loss_pct': 2.5,
            'packets_sent': packet_count,
            'packets_received': int(packet_count * 0.975),
        }
    
    def get_status(self) -> dict:
        """Get full station status."""
        return {
            'station_id': self.config.station_id,
            'latitude': self.config.latitude,
            'longitude': self.config.longitude,
            'altitude_m': self.config.altitude_m,
            'hardware': self.config.hardware,
            'uptime_seconds': self.uptime_seconds,
            'is_tracking': self.antenna.tracking_mode != "MANUAL",
            'active_frequencies': [f"{self.receiver.frequency_mhz:.3f} MHz"],
            'cpu_temp_c': self.telemetry.temperature_c,
            'cpu_usage_pct': 15 + random.gauss(0, 5),
            'disk_free_bytes': 28_000_000_000,
            'total_packets_decoded': self.total_packets,
        }


PACKET_TYPE_MAP = {
    "APRS": freesat_pb2.PACKET_APRS,
    "AX25": freesat_pb2.PACKET_AX25,
    "CCSDS": freesat_pb2.PACKET_CCSDS,
    "OpenOrbitLink": getattr(freesat_pb2, "PACKET_OPENORBITLINK", freesat_pb2.PACKET_DTN),
    "BEACON": freesat_pb2.PACKET_BEACON,
}


def tracking_mode_to_name(mode: int) -> str:
    if mode == freesat_pb2.AUTO_TRACK:
        return "AUTO_TRACK"
    if mode == freesat_pb2.PROGRAM_TRACK:
        return "PROGRAM_TRACK"
    if mode == freesat_pb2.PARK:
        return "PARK"
    return "MANUAL"


class OpenOrbitLinkServer(freesat_pb2_grpc.OpenOrbitLinkGroundStationServicer):
    """Async gRPC service that exposes telemetry, packet streams, and controls."""
    
    def __init__(self, station: GroundStationService, host: str = "0.0.0.0", port: int = 50051):
        self.station = station
        self.host = host
        self.port = port

    async def GetStatus(self, request, context):
        self.station.update_telemetry()
        status = self.station.get_status()
        return freesat_pb2.StationStatus(
            station_id=status["station_id"],
            latitude=status["latitude"],
            longitude=status["longitude"],
            altitude_m=status["altitude_m"],
            hardware=status["hardware"],
            uptime_seconds=status["uptime_seconds"],
            is_tracking=status["is_tracking"],
            active_frequencies=status["active_frequencies"],
            cpu_temp_c=float(status["cpu_temp_c"]),
            cpu_usage_pct=float(status["cpu_usage_pct"]),
            disk_free_bytes=status["disk_free_bytes"],
            total_packets_decoded=status["total_packets_decoded"],
        )

    async def GetTelemetry(self, request, context):
        self.station.update_telemetry()
        t = self.station.telemetry
        response = freesat_pb2.TelemetryResponse(
            signal_strength_dbm=round(t.signal_dbm, 2),
            noise_floor_dbm=round(t.noise_floor_dbm, 2),
            snr_db=round(t.snr_db, 2),
            frequency_mhz=self.station.receiver.frequency_mhz,
            doppler_shift_khz=round(t.doppler_khz, 3),
            ber=round(t.ber, 6),
            fec_corrections=t.fec_corrections,
            packets_received=t.packets_received,
            packets_errors=t.packets_errors,
            temperature_c=round(t.temperature_c, 1),
            timestamp_ms=t.timestamp_ms,
        )
        if request.include_history:
            response.history.extend(
                freesat_pb2.TelemetrySample(
                    timestamp_ms=sample["timestamp_ms"],
                    snr_db=sample["snr_db"],
                    signal_dbm=sample["signal_dbm"],
                    doppler_khz=sample["doppler_khz"],
                )
                for sample in self.station._telemetry_history
            )
        return response

    async def StreamPackets(self, request, context):
        frequency_filters = set(request.frequency_filters)
        for _ in range(60):
            self.station.update_telemetry()
            packet = self.station.generate_packet()
            if packet:
                freq = f"{packet['frequency_mhz']:.3f} MHz"
                if frequency_filters and freq not in frequency_filters:
                    await asyncio.sleep(1)
                    continue
                if request.decoded_only and not packet["decoded_text"]:
                    await asyncio.sleep(1)
                    continue
                yield freesat_pb2.PacketEvent(
                    timestamp_ms=packet["timestamp_ms"],
                    source_callsign=packet["source"],
                    destination=packet["destination"],
                    satellite_name=packet["satellite"],
                    norad_id=packet["norad_id"],
                    frequency_mhz=packet["frequency_mhz"],
                    snr_db=packet["snr_db"],
                    raw_data=packet["decoded_text"].encode("utf-8"),
                    decoded_text=packet["decoded_text"],
                    packet_type=PACKET_TYPE_MAP.get(packet["packet_type"], freesat_pb2.PACKET_UNKNOWN),
                    crc_valid=packet["crc_valid"],
                )
            await asyncio.sleep(1)

    async def StreamWaterfall(self, request, context):
        fps = max(1, min(request.update_rate_hz or 5, 20))
        self.station.set_frequency(
            request.center_frequency_mhz or self.station.receiver.frequency_mhz,
            request.bandwidth_khz or self.station.receiver.bandwidth_khz,
            self.station.receiver.modulation,
            self.station.receiver.gain_db,
            self.station.receiver.agc_enabled,
        )
        for _ in range(30 * fps):
            frame = self.station.generate_waterfall_frame()
            yield freesat_pb2.WaterfallFrame(
                timestamp_ms=frame["timestamp_ms"],
                center_frequency_mhz=frame["center_frequency_mhz"],
                bandwidth_khz=frame["bandwidth_khz"],
                power_spectrum_db=frame["power_spectrum_db"],
            )
            await asyncio.sleep(1.0 / fps)

    async def ControlAntenna(self, request, context):
        result = self.station.set_antenna(
            request.azimuth_deg,
            request.elevation_deg,
            tracking_mode_to_name(request.mode),
            request.target_norad_id,
        )
        return freesat_pb2.AntennaResponse(
            success=result["success"],
            current_azimuth=result["current_azimuth"],
            current_elevation=result["current_elevation"],
            active_mode=request.mode,
        )

    async def SetFrequency(self, request, context):
        result = self.station.set_frequency(
            request.frequency_mhz,
            request.bandwidth_khz,
            request.modulation,
            request.gain_db,
            request.agc_enabled,
        )
        return freesat_pb2.FrequencyResponse(
            success=result["success"],
            actual_frequency_mhz=result["actual_frequency_mhz"],
            ppm_correction=result["ppm_correction"],
        )

    async def RunSpeedTest(self, request, context):
        result = self.station.run_speed_test(
            request.packet_count or 100,
            request.packet_size_bytes or 256,
        )
        return freesat_pb2.SpeedTestResult(
            upload_bps=result["upload_bps"],
            download_bps=result["download_bps"],
            avg_latency_ms=result["avg_latency_ms"],
            jitter_ms=result["jitter_ms"],
            packet_loss_pct=result["packet_loss_pct"],
            packets_sent=result["packets_sent"],
            packets_received=result["packets_received"],
        )
    
    async def start(self):
        server = grpc.aio.server()
        freesat_pb2_grpc.add_OpenOrbitLinkGroundStationServicer_to_server(self, server)
        server.add_insecure_port(f"{self.host}:{self.port}")
        await server.start()
        logger.info(f"OpenOrbitLink Ground Station gRPC server listening on {self.host}:{self.port}")
        logger.info(f"Station: {self.station.config.station_id}")
        await server.wait_for_termination()


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='OpenOrbitLink Ground Station Server')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address')
    parser.add_argument('--station-id', default='FS-GS-001', help='Station identifier')
    parser.add_argument('--lat', type=float, default=28.6139, help='Station latitude')
    parser.add_argument('--lon', type=float, default=77.2090, help='Station longitude')
    args = parser.parse_args()
    
    config = StationConfig(
        station_id=args.station_id,
        latitude=args.lat,
        longitude=args.lon,
    )
    
    station = GroundStationService(config)
    server = OpenOrbitLinkServer(station, args.host, args.port)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server shutdown")


if __name__ == '__main__':
    main()
