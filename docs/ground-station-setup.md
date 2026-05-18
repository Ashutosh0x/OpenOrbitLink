# OpenOrbitLink Ground Station Setup Guide

## Overview

A OpenOrbitLink ground station is a community-operated relay node that bridges
satellite passes to the internet and local LoRa mesh networks. It includes
a **gRPC server** that provides real-time telemetry, packet streaming,
antenna control, and waterfall data to connected OpenOrbitLink Android apps.

**Total Cost: ~$250 | Power: ~$2/month**

## Hardware Required

| Item | Cost | Notes |
|------|------|-------|
| Raspberry Pi 4 (4GB) | $80 | ARMv8 Cortex-A72 |
| RTL-SDR V4 | $30 | R828D, 500kHz-1.766GHz |
| UHF Yagi Antenna | $80 | 400-500MHz, ~12dBi |
| LoRa Gateway (Heltec) | $25 | ESP32 + SX1276 |
| GPS Module (NEO-6M) | $15 | NMEA output |
| 32GB SD Card | $10 | Class 10 A1 |
| USB-C PSU 5V/3A | $10 | Official RPi |
| SMA Cables | $15 | Various adapters |

## Software Setup

### 1. Raspberry Pi OS
```bash
# Flash Raspberry Pi OS Lite (64-bit) to SD card
# Boot and SSH in

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git librtlsdr-dev
```

### 2. OpenOrbitLink Software
```bash
git clone https://github.com/OpenOrbitLink-project/OpenOrbitLink.git
cd OpenOrbitLink
python3 -m venv .venv
source .venv/bin/activate
pip install numpy sgp4 aiohttp pyyaml grpcio grpcio-tools
```

### 3. RTL-SDR Test
```bash
# Test RTL-SDR connection
rtl_test -t

# Quick FM receive test
rtl_fm -f 137.1e6 -s 48000 -g 40 - | aplay -r 48000 -f S16_LE
```

### 4. Start Relay Daemon
```bash
python -m ground_station.relay_daemon \
    --station-id FS-GS-YOUR-CALLSIGN \
    --lat YOUR_LATITUDE \
    --lon YOUR_LONGITUDE
```

### 5. Start gRPC Server
```bash
# Start the gRPC telemetry server on port 50051
python -m ground_station.grpc_server \
    --port 50051 \
    --station-id FS-GS-001 \
    --lat 28.6139 \
    --lon 77.2090
```

The Python server uses `grpc.aio` and the generated protobuf modules
`ground_station/freesat_pb2.py` and `ground_station/freesat_pb2_grpc.py`.
It provides 7 RPCs to OpenOrbitLink clients:

| RPC | Type | Description |
|:---|:---|:---|
| `GetStatus` | Unary | Station ID, uptime, hardware, location |
| `GetTelemetry` | Unary | Signal strength, SNR, Doppler, BER, temp |
| `StreamPackets` | Server stream | Live decoded packet feed (APRS, AX.25, etc.) |
| `StreamWaterfall` | Server stream | FFT waterfall spectrum data |
| `ControlAntenna` | Unary | Set azimuth/elevation, auto-track mode |
| `SetFrequency` | Unary | Tune receiver frequency, modulation, gain |
| `RunSpeedTest` | Unary | Measure satellite link throughput |

### 6. Docker (Alternative)
```bash
cd docker
docker-compose up -d ground-station
```

## Connecting the Android App

1. Ensure your phone is on the same WiFi network as the RPi
2. Open OpenOrbitLink app > Hub > Ground Station
3. Enter the RPi's IP address and port 50051
4. The app will display:
   - Live telemetry (signal strength, temperature, packet count)
   - Antenna control sliders (azimuth/elevation)
   - Frequency tuning with ISS APRS / NOAA presets
   - Decoded packet feed in real-time

## Antenna Placement

- Mount UHF Yagi with clear view of sky (no obstructions above 10 deg)
- Point South (Northern hemisphere) or North (Southern hemisphere)
- Minimum 3m above ground level
- Use low-loss coax cable (RG-213 or LMR-400)

## SatNOGS Integration

1. Register at https://network.satnogs.org
2. Get your station ID and API token
3. Configure in ground station settings

## Protobuf API Reference

The full service definition is in `ground_station/freesat.proto`:
- 15 message types covering telemetry, packets, antenna, frequency
- 2 enums: `PacketType` (7 values) and `TrackingMode` (4 values)
- Compatible with any gRPC client (Python, Kotlin, Go, etc.)

## Monitoring

The gRPC server logs startup, station configuration, telemetry activity, and
control commands.

Check logs:
```bash
journalctl -u OpenOrbitLink-ground-station -f
```
