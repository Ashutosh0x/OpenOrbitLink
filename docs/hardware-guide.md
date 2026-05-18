# OpenOrbitLink Hardware Guide

## Device Paths

### Path A: Direct NTN (Cost: $0)
Phones with built-in NTN satellite modem.

| Phone | Chip | Standard | Capability |
|-------|------|----------|------------|
| Pixel 9/10 | Snapdragon X80 | NB-NTN R17 | Satellite messaging |
| Galaxy S25 | Exynos 5300 | 3GPP R17 | Satellite messaging |
| Galaxy S26 | Exynos 5410 | 3GPP R17-19 | Voice+video over sat |

**Setup**: Install OpenOrbitLink app > enable satellite mode > ready.

### Path B: USB SDR (Cost: ~$80)
External SDR receiver connected via USB OTG.

| Item | Model | Cost |
|------|-------|------|
| SDR | RTL-SDR Blog V4 | $30 |
| Antenna | L-band Yagi / VHF dipole | $50 |
| USB OTG | USB-C to USB-A adapter | $5 |

**Setup**: Plug SDR into phone via OTG > launch OpenOrbitLink > tune frequency.

### Path C: LoRa Mesh (Cost: ~$10)
LoRa radio module paired via Bluetooth.

| Item | Model | Cost |
|------|-------|------|
| LoRa Board | Heltec LoRa 32 V3 | $25 |
| _or_ LoRa Module | SX1276 bare module | $10 |

**Setup**: Flash OpenOrbitLink LoRa firmware > pair via Bluetooth > relay through mesh.

## In-App Setup Wizard

The OpenOrbitLink Android app includes a **Hardware Setup Wizard** screen
(accessible from Hub > Hardware Setup) that provides:

- **Interactive path selection** — tap to choose NTN, SDR, or LoRa
- **Step-by-step checklists** — expandable setup instructions per path
- **Hardware verification** — USB device detection for SDR
- **Cost BOM** — per-path bill of materials with total pricing
- **Completion tracking** — check off steps as you complete them

## Sky Scanner (Antenna Placement Aid)

Before mounting antennas, use the **Sky Scanner** screen (Hub > Sky Scan):

- **Polar sky plot** — shows compass-aligned sky visibility from your location
- **Obstruction analysis** — identifies buildings/trees blocking satellite paths
- **ISS pass arc** — predicted satellite trajectory overlay
- **Radar sweep** — animated scanning beam with real-time sky percentage
- **Optimal pointing** — recommended azimuth/elevation for best pass quality

## Antenna Designs

### VHF Dipole (137 MHz — NOAA)
- Total length: 1.04m (each leg: 52cm)
- Material: Copper wire or aluminium rod
- Connector: BNC or SMA
- Gain: ~2dBi

### UHF Yagi (435 MHz — Amateur)
- Elements: 5-element Yagi
- Boom length: ~60cm
- Gain: ~10dBi
- Pattern: Directional

### Helical (1.7 GHz — L-band)
- Turns: 8
- Diameter: 56mm per turn
- Length: 280mm
- Gain: ~12dBi
- Polarization: RHCP (matches most LEO sats)

## SDR Comparison

| Feature | RTL-SDR V4 | HackRF One | Airspy Mini |
|---------|-----------|------------|-------------|
| Freq Range | 500kHz-1.7GHz | 1MHz-6GHz | 24-1700MHz |
| Bandwidth | 3.2MHz | 20MHz | 6MHz |
| TX | No | Yes (half) | No |
| Bit Depth | 8-bit | 8-bit | 12-bit |
| Cost | $30 | $350 | $99 |
| OpenOrbitLink Role | Receive | Experimental TX | High-quality RX |
