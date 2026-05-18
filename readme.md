# OpenOrbitLink

OpenOrbitLink is an open research stack for delay-tolerant messaging over LoRa,
amateur packet radio, mesh relays, and ground-station networks.

It is not a magic phone-to-satellite transmitter. Android phones cannot transmit
arbitrary VHF/UHF/LoRa RF by themselves, RTL-SDR dongles are receive-only, and
amateur satellite paths have strict licensing and plaintext rules. This repo now
treats those constraints as protocol behavior, not footnotes.

## What Works Today

| Path | Status | Encryption | License | Notes |
|:---|:---|:---:|:---:|:---|
| Android to external LoRa node to ISM satellite/ground receiver | Buildable prototype | Yes | Region rules only | Best open path for private short text/DTN payloads. |
| TinyGS-compatible ground station receive/poll | Adapter added | N/A | No TX license for RX | Use existing station infrastructure instead of inventing a parallel network. |
| ISS APRS / amateur AX.25 | Decode and standards-shaped frame helpers | No | Ham TX required | Only valid APRS/AX.25 traffic; not arbitrary encrypted chat. |
| RTL-SDR V4 | Receive only | N/A | RX usually license-free | Good for NOAA/APRS receive demos, not uplink. |
| VoIP/PSTN bridge through internet gateway | Architectural option | Internet leg can be encrypted | Telecom provider required | Needs internet somewhere in the mesh plus a legal SIP/PSTN trunk. |
| Carrier NTN (Pixel 9+, Galaxy S25+) | Convergence target | App-layer | Carrier plan required | Closed uplink; OpenOrbitLink can bridge DTN queue to NTN gateway. |

## Why OpenOrbitLink still matters alongside NTN

Carrier NTN (Starlink/T-Mobile, Skylo/Google/Verizon, and Galaxy operator
rollouts) is real on flagship phones, but it is carrier-gated, region-gated,
and optimized first for emergency messaging, SMS, and selected low-bandwidth
apps. In India, direct-to-device carrier NTN remains a regulatory and operator
integration target: TRAI had an open satellite network authorization
consultation dated 2026-04-08 and released satellite spectrum assignment
recommendations on 2026-05-15, but OpenOrbitLink should not assume consumer D2D
availability there yet.

OpenOrbitLink fills the gap: open ISM uplink, arbitrary DTN payloads,
end-to-end encryption on ISM bands, no carrier dependency, and a queue that can
eventually egress through a carrier NTN gateway when one is available.

## Core Features

- Band-aware packet format with `TransmitBand` and encrypted-payload guard.
- Security policy that blocks ciphertext on amateur-band transmissions.
- Local license gate for callsign syntax, operator attestation, and amateur TX.
- DTN queue with band metadata and encrypted/plaintext policy enforcement.
- BPv7/BPSec helpers that reject BCB confidentiality blocks on amateur bands.
- LoRa/FOSSA-sized frame encoder with 80-byte frame limit.
- TinyGS API client scaffold using Bearer auth and base64 TX frame payloads.
- TLE fetcher that writes metadata JSON and warns on stale orbital data.
- Link-budget simulator with honest TX paths and effective throughput analysis.
- Offline `demo.py` simulation for contributors without RF hardware.

## Security Model

OpenOrbitLink separates integrity from confidentiality:

| Band | Confidentiality | Integrity/Auth | Reason |
|:---|:---:|:---:|:---|
| Amateur | Blocked | Allowed | Amateur rules prohibit obscuring message meaning. |
| ISM LoRa | Allowed | Allowed | Subject to regional ISM power, duty-cycle, and device rules. |
| Licensed private/commercial | Allowed | Allowed | Must follow the license or carrier agreement. |
| Carrier NTN | Allowed | Allowed | Requires operator service and standard phone modem support. |
| Receive-only | N/A | N/A | No transmit path exists. |

The Python crypto API now requires a band:

```python
crypto.encrypt(b"hello", key, band="ism")       # allowed
crypto.encrypt(b"hello", key, band="amateur")   # raises EncryptionPolicyError
```

## Link Budget Reality

The previous docs modeled "200 mW phone TX" to ISS. That path does not exist.
The simulator now defaults to an external LoRa ISM uplink.

| Path | TX Capable | Default Power | Frequency | Role |
|:---|:---:|:---:|:---:|:---|
| `LORA_ISM_UPLINK` | Yes | 100 mW | 868.1 MHz | External LoRa node satellite/mesh uplink. |
| `HAM_SDR_UPLINK` | Yes | 1 W | 145.825 MHz | Licensed amateur station only. |
| `HACKRF_EXPERIMENTAL` | Yes | 25 mW | 435 MHz | Lab path needing filtering/amplification/legal review. |
| `CARRIER_NTN` | No open uplink | Carrier-managed | NTN bands | Closed operator path for future DTN gateway egress. |
| `ANDROID_NTN` | No app RF | Carrier-managed | NTN bands | Compatibility alias for the carrier NTN stack. |
| `RTL_SDR_RX_ONLY` | No | N/A | VHF/UHF RX | Receive and decode only. |

At 700 bps, a 256-byte packet with the current 21-byte header, 32-byte FEC
field, and 2-byte CRC takes about 3.55 seconds on air. Effective payload rate is
about 577 bps before any additional AX.25, LoRa, duty-cycle, retry, or satellite
access-window overhead.

## Legal Guardrails

- Amateur-band TX requires a valid amateur license and station identification.
- Amateur-band payloads must be plaintext; use BIB/integrity, not BCB/encryption.
- APRS support is for valid AX.25/APRS packets, not arbitrary encrypted chat.
- ISM use still depends on country-specific frequency, power, and duty-cycle limits.
- PSTN/Jio/Airtel calling is not possible directly from open LoRa/APRS satellite
  paths. It requires an internet VoIP bridge and a legal SIP/PSTN trunk.

See [docs/regulatory-compliance.md](docs/regulatory-compliance.md) and
[docs/ntn-comparison.md](docs/ntn-comparison.md).

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows PowerShell users can also use Activate.ps1
pip install -r requirements.txt

python -m pytest -q
python demo.py
python simulation/link_budget.py
python scripts/fetch_tle.py --all-openorbitlink --include-fossa
```

## Key References

- FCC amateur prohibited transmissions: <https://www.ecfr.gov/current/title-47/chapter-I/subchapter-D/part-97/subpart-B/section-97.113>
- Android SatelliteManager API: <https://developer.android.com/reference/android/telephony/satellite/SatelliteManager>
- Google Pixel Satellite SOS availability: <https://support.google.com/pixelphone/answer/15254448>
- T-Mobile T-Satellite service limits: <https://www.t-mobile.com/coverage/satellite-phone-service>
- TRAI satellite spectrum recommendations, 2026-05-15: <https://trai.gov.in/notifications/press-release/trai-releases-recommendations-terms-and-conditions-assignment-spectrum>
- CelesTrak GP/TLE query format: <https://celestrak.org/NORAD/documentation/gp-data-formats.php>
- TinyGS programmatic API notes: <https://github.com/tinygs/tinyGS/wiki/Programmatic-API>
- FOSSA LoRa/ISM FAQ: <https://fossa.systems/frequently-asked-questions/>

## License

GPLv3. This is research software; check local law before transmitting.
