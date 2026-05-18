# Regulatory Compliance Matrix

This is engineering guidance, not legal advice. Operators must check current
rules in their country before transmitting.

## Summary

| Path | Encryption | Callsign | Commercial/PSTN | Project Behavior |
|:---|:---:|:---:|:---:|:---|
| Amateur APRS/AX.25 | No | Required | No | `LicenseGate` + packet/BPSec encryption block. |
| ISM LoRa | Yes | No ham callsign | No carrier PSTN by itself | Allowed, subject to regional device limits. |
| Licensed private/commercial | Yes | License-specific | License-specific | Allowed only as an explicitly selected band. |
| Carrier NTN | Yes | No ham callsign | Carrier-provided | Treated as carrier path, not open RF. |
| Receive-only SDR | N/A | No TX | N/A | Cannot be selected for transmit. |

## United States

| Area | Practical Rule | OpenOrbitLink Control |
|:---|:---|:---|
| Amateur encryption | FCC Part 97 prohibits messages encoded for the purpose of obscuring meaning. | `BandType.AMATEUR` rejects encrypted packets and BPSec BCBs. |
| Amateur ID | Amateur stations identify with their assigned call sign. | Callsign syntax gate before amateur TX routing. |
| Amateur commercial traffic | Amateur service must not substitute for services normally furnished by other radio services. | `purpose="commercial"` and `purpose="pstn"` are blocked on amateur. |
| ISM | Device, frequency, power, and duty-cycle rules vary by band. | Docs avoid universal "free spectrum" claims; deployments must configure region. |

Reference: <https://www.ecfr.gov/current/title-47/chapter-I/subchapter-D/part-97/subpart-B/section-97.113>

## India

| Area | Practical Rule | OpenOrbitLink Control |
|:---|:---|:---|
| Amateur TX | Requires an amateur radio license and station identification. | Callsign and attestation required for amateur TX. |
| Amateur encryption | Treat amateur satellite traffic as plaintext-only unless a regulator explicitly permits otherwise. | Same amateur encryption block as the US. |
| ISM LoRa | Region-specific channels and power limits apply. | LoRa path is separate from amateur path and must be configured for India. |
| PSTN calls | Requires licensed telecom interconnect. | No direct satellite-to-Jio/Airtel claim; use only legal SIP/PSTN gateway when internet is reachable. |

## European Union

| Area | Practical Rule | OpenOrbitLink Control |
|:---|:---|:---|
| Amateur TX | National license and CEPT arrangements control operator privileges. | Callsign and attestation required. |
| ISM LoRa | EU 868 MHz sub-band duty-cycle and power constraints apply. | Link config must enforce regional radio settings outside this protocol layer. |
| Encryption | ISM/private links can carry encrypted payloads; amateur should remain plaintext. | Band-aware encryption policy. |

## Southeast Asia

| Area | Practical Rule | OpenOrbitLink Control |
|:---|:---|:---|
| Amateur TX | Country-by-country licensing and reciprocal privileges vary. | Local attestation required; country regex can be extended. |
| ISM LoRa | 433/868/915 availability differs by country. | Do not assume global FOSSA/TinyGS frequency compatibility. |
| Emergency use | Emergency telecom rules differ by regulator. | Product copy frames OpenOrbitLink as asynchronous messaging, not guaranteed emergency dispatch. |

## Required UX Guardrails

- Ask users to choose a path before transmitting.
- Show "plaintext only" on amateur paths.
- Ask for callsign and license confirmation before amateur TX.
- Show estimated delivery windows; do not show cellular-style dial tone for DTN voice.
- Label Codec2 as voice messaging unless a real-time, legal, same-footprint path exists.
- Show TLE age warnings before pass predictions when TLE data is older than 3 days.

## Implementation Hooks

| Hook | File |
|:---|:---|
| Band policy | `security/__init__.py` |
| BPSec BCB guard | `security/bpsec.py` |
| Packet band field | `protocol/packet.py` |
| License gate | `protocol/license.py` |
| Mesh route guard | `protocol/mesh.py` |
| TLE stale warnings | `scripts/fetch_tle.py`, `ai/orbital_predictor.py` |
