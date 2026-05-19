# OpenOrbitLink Ground Station -- RPi + LoRa Setup Guide

## Bill of Materials

| Component | Specification | Price (INR) | Source |
|-----------|--------------|-------------|--------|
| Raspberry Pi Zero 2W | 1GHz quad-core, 512MB RAM, WiFi | ~1,800 | robu.in / amazon.in |
| RA-02 SX1276 Module | 868 MHz, SPI, 20 dBm max | ~600 | robu.in / aliexpress |
| Quarter-wave antenna | 8.6 cm copper wire + SMA | ~200 | DIY |
| MicroSD card | 16GB+ Class 10 | ~350 | amazon.in |
| USB power supply | 5V 2.5A micro-USB | ~300 | amazon.in |
| Jumper wires | Female-female, 7 wires | ~50 | robu.in |
| **Total** | | **~3,300** | |

## Wiring Diagram

```
RA-02 SX1276          Raspberry Pi Zero 2W
+-----------+         +-------------------+
| VCC  (3.3V) |------>| Pin 1  (3.3V)     |
| GND        |------>| Pin 6  (GND)      |
| SCK        |------>| Pin 23 (SPI0_SCLK) GPIO 11 |
| MISO       |------>| Pin 21 (SPI0_MISO) GPIO  9 |
| MOSI       |------>| Pin 19 (SPI0_MOSI) GPIO 10 |
| NSS        |------>| Pin 24 (SPI0_CE0)  GPIO  8 |
| DIO0       |------>| Pin 18            GPIO 24 |
| RST        |------>| Pin 22            GPIO 25 |
+-----------+         +-------------------+
```

CAUTION: The RA-02 module operates at 3.3V ONLY. DO NOT connect to 5V.

## Software Setup

### 1. Flash Raspberry Pi OS

```bash
# Use Raspberry Pi Imager to flash Raspberry Pi OS Lite (64-bit)
# Enable SSH during imaging (Ctrl+Shift+X in imager)
# Set hostname: openorbitlink-gs
# Set username/password
# Configure WiFi
```

### 2. Enable SPI

```bash
sudo raspi-config
# Navigate to: Interface Options -> SPI -> Enable
# Reboot
sudo reboot
```

Verify SPI is enabled:
```bash
ls /dev/spidev*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

### 3. Install Dependencies

```bash
# System packages
sudo apt update
sudo apt install -y python3-pip python3-venv git

# Create virtualenv
python3 -m venv ~/ool-env
source ~/ool-env/bin/activate

# Install LoRa driver
pip install LoRaRF

# Install OpenOrbitLink dependencies
pip install skyfield aiohttp pyyaml

# Clone repo
git clone https://github.com/Ashutosh0x/OpenOrbitLink.git
cd OpenOrbitLink
pip install -r requirements.txt
```

### 4. Test LoRa Module

```python
# test_lora.py -- run this to verify hardware
from LoRaRF import SX1276, LoRaSPI, LoRaGPIO

lora = SX1276()
spi = LoRaSPI(0, 0)           # Bus 0, CS 0
gpio = LoRaGPIO(25, 24)       # RST=GPIO25, DIO0=GPIO24

if lora.begin(spi, gpio):
    print("SX1276 initialized successfully!")
    lora.setFrequency(868000000)
    lora.setSpreadingFactor(12)
    lora.setBandwidth(7)       # 125 kHz
    lora.setTxPower(14)        # 14 dBm = 25 mW

    # Send test packet
    lora.beginPacket()
    lora.write(list(b"OpenOrbitLink Ground Station Test"))
    lora.endPacket()
    print("Test packet transmitted on 868.000 MHz")
else:
    print("ERROR: SX1276 not detected. Check wiring!")
```

```bash
python3 test_lora.py
```

### 5. Antenna Construction

868 MHz quarter-wave antenna:

```
Length = c / (4 * f) = 299792458 / (4 * 868000000) = 0.0864 m = 8.64 cm

Materials:
- 8.6 cm copper wire (stripped 14-16 AWG)
- SMA connector or solder directly to RA-02 ANT pad

Construction:
1. Cut copper wire to exactly 8.6 cm
2. Solder to the antenna pad on RA-02 module
3. Orient vertically for omnidirectional coverage
4. For satellite uplink: point straight up (zenith)

For improved gain (optional):
- Ground plane antenna: 4 radials at 45 degrees, each 8.6 cm
- Adds ~3 dBi gain over bare wire
- Total cost: ~INR 300 with SMA connector
```

### 6. Start Ground Station Daemon

```bash
cd ~/OpenOrbitLink
source ~/ool-env/bin/activate

# Fetch latest TLE data
python scripts/fetch_tle.py --all-openorbitlink --include-fossa

# Start daemon
python -m ground_station.relay_daemon \
    --station-id "OOL-GS-$(hostname)" \
    --lat 28.6139 \
    --lon 77.2090 \
    --alt 216
```

### 7. Systemd Service (Auto-Start)

Create `/etc/systemd/system/openorbitlink-gs.service`:

```ini
[Unit]
Description=OpenOrbitLink Ground Station Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/OpenOrbitLink
ExecStart=/home/pi/ool-env/bin/python -m ground_station.relay_daemon \
    --station-id "OOL-GS-001" \
    --lat 28.6139 --lon 77.2090 --alt 216
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable openorbitlink-gs
sudo systemctl start openorbitlink-gs

# Check status
sudo systemctl status openorbitlink-gs

# View logs
journalctl -u openorbitlink-gs -f
```

### 8. TLE Auto-Update Cron

```bash
# Update TLE data daily at 3 AM
crontab -e
# Add:
0 3 * * * cd /home/pi/OpenOrbitLink && /home/pi/ool-env/bin/python scripts/fetch_tle.py --all-openorbitlink --include-fossa
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| SPI device not found | Run `sudo raspi-config` and enable SPI |
| SX1276 not detected | Check VCC=3.3V, verify GND connection, try swapping MISO/MOSI |
| No TX output | Verify antenna connection, check `lora.setTxPower(14)` |
| Poor range | Increase SF (12=max range), add ground plane antenna |
| Daemon crashes | Check `journalctl -u openorbitlink-gs` for errors |

## TinyGS Receive-Only Mode

If you don't have uplink hardware yet, you can run a TinyGS receive-only
station to verify the downlink path:

1. Flash TinyGS firmware on an ESP32 + SX1276
2. Register at https://tinygs.com
3. Point antenna at sky
4. Received FOSSASAT packets appear in TinyGS dashboard
5. Use `ground_station/tinygs_client.py` to poll and route to inbox

This proves the satellite-to-ground path works before investing in
the full uplink setup.
