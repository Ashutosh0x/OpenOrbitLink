# NTN Path Comparison

Last checked: 2026-05-18.

OpenOrbitLink treats NTN as a convergence target, not a replacement for open
ISM or licensed amateur paths. The same DTN bundle can sit in the queue and
egress through whichever legal path is actually available: LoRa/ISM first,
amateur only when plaintext and licensed, and carrier NTN only through an
operator-controlled gateway.

## Path Family 1: ISM / Open Uplink

The open path is an Android app plus an external LoRa node, typically in a
regional sub-GHz ISM/SRD band such as 865-867 MHz in India, 868 MHz in parts of
Europe, or 915 MHz in other markets. The phone is not the RF transmitter; it
queues and encrypts the DTN payload, then hands it to the LoRa node over USB,
Bluetooth, or another local link.

This is the best fit for arbitrary OpenOrbitLink payloads. Payload encryption
is allowed at the application layer, subject to regional power, channel, and
duty-cycle rules. The project models this as `TransmitBand.ISM` and the
`LORA_ISM_UPLINK` link-budget profile.

Hardware requirements are modest: an Android phone, a LoRa radio node, antenna,
power source, and a matching open satellite or ground receiver path such as a
TinyGS/FOSSA-style station. In India this is the practical near-term path, but
the exact frequency and power plan must follow local WPC/short-range-device
rules rather than a globally hard-coded "868 MHz" assumption.

## Path Family 2: Amateur Radio

The amateur path is a licensed operator using an HT, TNC, SDR station, or other
legal amateur transmitter for AX.25/APRS-like traffic, including ISS APRS and
AMSAT repeaters where the satellite and band plan permit it.

OpenOrbitLink only allows plaintext plus integrity on this path. BPSec BIB
integrity/authentication is acceptable as metadata, but BCB confidentiality or
other ciphertext intended to obscure message meaning is blocked by policy.
Commercial, carrier gateway, PSTN, or paid traffic must not use the amateur
path.

Hardware requirements include a valid amateur license, callsign, suitable VHF
or UHF radio hardware, antenna, and operating knowledge. The simulator models a
licensed 145.825 MHz AX.25-style path as `HAM_SDR_UPLINK`, while receive-only
hardware such as RTL-SDR remains decode-only.

In India, this path requires an amateur radio license and normal amateur
operating constraints. It is useful for demos, emergency-style plaintext packet
experiments, and interoperability with existing amateur infrastructure, not for
private encrypted chat.

## Path Family 3: Carrier NTN

Carrier NTN is the closed smartphone satellite path: T-Mobile/Starlink,
Skylo-powered Pixel and Verizon/Samsung services, Virgin Media O2/Starlink,
and similar mobile-operator deployments. These systems are real, but apps do
not get raw satellite RF access. The phone modem and carrier core decide when
satellite service is available and what services can run.

Current public deployments are still region, carrier, plan, OS, and device
gated. Google documents Satellite SOS for Pixel devices since Pixel 9 except
Pixel 9a, with availability in the US, Canada, Puerto Rico, Australia, much of
Europe, and the UK, but not India. T-Mobile's T-Satellite now supports texting
and selected satellite-ready apps in supported countries, with limited speeds
and possible delays. Samsung states that Galaxy satellite capabilities,
including Galaxy S26 support, roll out by operator, model, OS version, market,
and regulation.

For OpenOrbitLink, carrier NTN should be modeled as a DTN egress gateway:
`TransmitBand.CARRIER_NTN` and `TxPath.CARRIER_NTN` mean "handoff to a carrier
SIP/API/SCS gateway", not "transmit RF from the app". Application-layer
encryption is allowed for payloads the carrier service can carry, but the
carrier still controls registration, entitlement, routing, supported apps, and
lawful service limits.

Hardware requirements are a supported handset and service plan, such as Pixel
9/10 class devices or Galaxy S25/S26 class devices where the operator has
enabled satellite service. Android exposes a public satellite feature flag and
`SatelliteManager` in API 36; OpenOrbitLink probes for this capability and shows
the user whether carrier NTN is a possible path on the current device.

India status is still "do not assume availability" for consumer direct-to-device
carrier NTN. TRAI released a satellite communication network authorization
consultation on 2026-04-08 and satellite spectrum assignment recommendations on
2026-05-15. That is movement, not an app-visible guarantee that Pixel, Galaxy,
Starlink, Skylo, or carrier D2D service works for OpenOrbitLink users in India.

## Summary Matrix

| Path family | Transmit control | Encryption | India status | Hardware |
|:---|:---|:---|:---|:---|
| ISM / open LoRa | User-controlled external radio | Allowed | Available under local ISM/SRD rules | Android phone plus LoRa node and antenna |
| Amateur AX.25/APRS | Licensed amateur station | Confidentiality blocked; integrity only | Requires amateur license | HT/TNC/SDR station and callsign |
| Carrier NTN | Carrier-controlled modem and core | App-layer possible where service permits | Regulatory/operator integration pending | Supported Pixel/Galaxy class phone plus carrier plan |

## References

- Android `SatelliteManager`: <https://developer.android.com/reference/android/telephony/satellite/SatelliteManager>
- Android satellite feature flag in AOSP: <https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-platform-15.0.0_r7/data/etc/android.hardware.telephony.satellite.xml>
- Google Pixel Satellite SOS availability: <https://support.google.com/pixelphone/answer/15254448>
- T-Mobile T-Satellite service limits: <https://www.t-mobile.com/coverage/satellite-phone-service>
- Samsung Galaxy satellite support announcement: <https://news.samsung.com/uk/samsung-brings-satellite-communication-support-to-galaxy-smartphones-across-the-globe>
- Skylo Pixel 10 / Pixel Watch 4 announcement: <https://www.skylo.tech/newsroom/google-and-skylo-expand-satellite-connectivity-to-pixel-10-series-and-unveil-pixel-watch-4>
- Verizon/Skylo Android satellite texting announcement: <https://www.skylo.tech/newsroom/verizon-customers-are-the-first-in-the-us-to-enjoy-satellite-texting-to-any-device-with-select-android-smartphones>
- 3GPP NTN overview: <https://www.3gpp.org/technologies/ntn-overview>
- TRAI 2026 satellite network authorization consultation: <https://trai.gov.in/consultation-paper-framework-satellite-communication-network-authorisation-and-assignment-spectrum>
- TRAI 2026 satellite spectrum recommendations: <https://trai.gov.in/notifications/press-release/trai-releases-recommendations-terms-and-conditions-assignment-spectrum>
