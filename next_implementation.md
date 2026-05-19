42%
Overall complete
58%
Work remaining
~8 mo
Solo dev estimate
3
Satellite paths
Done in OOL
Partial / scaffold
Not started
hard
Complex work
medium
Medium effort
easy
Easy
Target satellites: 
FOSSASAT-2E 
ISS APRS 
Dream Big (×6)
FastAPI backend + JWT auth gate done
Register, login, /send, /inbox, /queue, /status — all functional
Per-user DTN queue (SQLite) done
Priority queue, bcrypt passwords, AES-256-GCM Keystore token storage
ISM duty cycle enforcer (1% / 36 sec/hr) done
Rate limiter with per-user fair-share allocation + compliance logging
80-byte LoRa / FOSSA-sized frame encoder done
Matches FOSSASAT-2E packet size exactly. Golay FEC, 2-byte CRC, 21-byte header
Band-aware crypto policy (ISM vs amateur) done
EncryptionPolicyError on amateur band — correct regulatory behaviour
BPv7 / BPSec full implementation medium
Helpers exist but full RFC 9171 compliance + BCB block handling needs completion
Multi-hop DTN routing table hard
Epidemic/spray-and-wait routing for mesh relay hops. Not yet implemented.
FOSSA uplink: 868 / 915 / 400 MHz ISM. 80-byte packets @ 300 bps. Node sends → satellite stores → downlinks to FOSSA ground stations → your backend polls via FOSSA API.
TinyGS API client scaffold (bearer auth + base64 frames) done
ground_station/ module exists with bearer auth and frame encoding
TLE fetcher for FOSSASAT-2E orbital prediction done
scripts/fetch_tle.py --include-fossa writes TLE JSON with staleness warning
Satellite pass scheduler (SGP4 → next pass window) medium
SGP4 library integrated but automated "queue flush on next pass" logic missing. Need: compute next overhead window → schedule TX burst within duty cycle budget.
LoRa node hardware driver (SX1276 / SX1262) hard
Physical Raspberry Pi + LoRa HAT driver for 868 MHz ISM uplink. RadioLib or pyLoRa integration needed. This is the hardware-side TX engine that actually talks to the satellite.
Doppler correction for LoRa uplink medium
FOSSASAT-2E moves at ~7.5 km/s → ±3 kHz Doppler shift at 868 MHz. Need real-time frequency offset calculation during pass window and dynamic chirp adjustment.
FOSSA downlink poller + inbox delivery medium
Poll FOSSA cloud API for downlinked messages → decode frame → route to recipient's /inbox. This closes the DTN loop: message goes up through LoRa, comes back down through FOSSA ground network.
End-to-end integration test (offline → live) medium
Extend demo.py simulation to replay a FOSSASAT pass and verify full message lifecycle: Android → FastAPI → LoRa queue → TX window → FOSSA API → inbox
ISS APRS digipeater RS0ISS: uplink 145.825 MHz, downlink 145.825 MHz. AX.25 packet, 1200 bps AFSK, 300 mW recommended TX. No encryption. ~6–8 passes/day over India.
AX.25 / APRS frame decode helpers done
protocol/ module has decode and frame helpers for ISS APRS traffic
Amateur band plaintext enforcement done
EncryptionPolicyError correctly blocks ciphertext on amateur band
HAM_SDR_UPLINK driver (1W VHF 145.825 MHz) hard
HackRF / RTL-SDR TX path at 145.825 MHz. Legal only with amateur callsign. Need: PTT logic, 1200 bps AFSK modulation (Bell 202), AX.25 framing, frequency correction for Doppler.
Callsign validation gate for APRS TX easy
Local license gate exists but needs callsign syntax check + SSID assignment before any APRS packet is transmitted.
APRS-IS internet bridge (fallback) easy
When ISS pass not available, gate APRS packets through APRS-IS internet network (aprs.fi API). Provides instant delivery when internet is up — graceful fallback before DTN TX.
ISS pass prediction display in Android app medium
Show next ISS pass time + elevation angle. Use TLE from CelesTrak. Notify user "satellite overhead in 8 min — queued messages will transmit."
JWT auth gate + Android Keystore AES-256-GCM done
Login, invite code, auto-logout on 401, EncryptedSharedPreferences
Basic send/inbox API client done
Bearer token, all endpoints wired
Satellite pass timeline widget medium
Live Jetpack Compose UI showing next FOSSA + ISS pass time, duration, max elevation. Drives user expectation: "Your message will send in ~14 min."
Message status tracking (queued → transmitted → delivered) medium
Three-state indicator per message. "Queued" = in SQLite. "Transmitted" = LoRa TX confirmed. "Delivered" = downlink acknowledged from FOSSA/APRS-IS.
Offline compose + queue (no internet needed) medium
User composes message without internet. App stores locally. Syncs to backend when connected. This is the core offline-first satellite messaging UX.
PTT voice message recording (Codec2 700C) medium
Android mic → Codec2 NDK encode → 80-byte chunks → DTN queue. Already have codec2-android/ module — needs UI integration and chunking logic.
Duty cycle gauge + TX budget display easy
Show remaining TX seconds this hour across all users. Helps users understand latency — "only 12 sec of airtime left today on this node."
This is the hardest part. Every software module is useless without a physical LoRa node (RPi + SX1276 HAT) pointed at the sky. Budget: ~₹3,000–8,000 for hardware.
Hardware/ folder + RPi setup docs done
hardware/ directory exists in repo
RPi LoRa HAT driver (SX1276, 868 MHz) hard
Python driver for Semtech SX1276 over SPI. RadioLib Python bindings or pyLoRa. Must handle: spreading factor selection, bandwidth, Doppler pre-correction, duty cycle timer.
Ground station daemon (systemd service) medium
Always-on service: polls backend for outbound queue → waits for satellite pass window → bursts packets → reports TX result. Runs on RPi at 868 MHz ISM.
Antenna setup guide (868 MHz quarter-wave) easy
Simple wire antenna (8.6 cm for 868 MHz). Document in hardware/. Total cost: ~₹200 copper wire + SO-239 connector.
Docker Compose ground station profile easy
Add ground_station profile to docker/compose.yml. One command to start both backend + station daemon on RPi.
TinyGS fallback (receive-only mode) easy
If no uplink hardware, run in TinyGS receive-only mode to at least receive downlink packets and verify the satellite path is working.
Post-TRAI India regulatory approval. When Starlink/Airtel NTN goes live commercially, OOL DTN queue egresses through CARRIER_NTN gateway instead of LoRa. Already architecturally planned.
CARRIER_NTN path defined in link budget done
Architectural placeholder exists. simulation/link_budget.py includes the path.
Android SatelliteManager API integration (Pixel 9+ / Galaxy S25+) hard
android.telephony.satellite.SatelliteManager. Send DTN payload as SMS over carrier NTN when CARRIER_NTN path available. Requires carrier plan + approved phone modem.
DTN → NTN gateway bridge logic hard
When internet is available via NTN, egress the SQLite DTN queue through NTN gateway instead of LoRa. Priority: NTN (if available) → LoRa ISM → APRS (plaintext fallback).
OQ Technology ERMIS IoT bridge (Transporter-16 sats) medium
Once OQ Technology opens commercial API for ERMIS-1/2/3 (5G NTN IoT), integrate as third egress path. Direct-to-device emergency messaging on standard smartphones.
Suggested next 3 actions (priority order)
1. Build the satellite pass scheduler — integrate SGP4 → compute next FOSSASAT-2E overhead window → auto-flush queue during pass. This unblocks everything downstream.
2. Write the RPi SX1276 LoRa driver — even a basic 868 MHz TX test proves the physical uplink path. Use pyLoRa or RadioLib Python bindings. Buy hardware: RPi Zero 2W + RA-02 module (~₹2,500 total).
3. Add the satellite pass timeline widget to Android — it costs you 1–2 days of Compose work and immediately makes the app understandable to beta users.
Here's the honest full picture. Click each phase to expand the task breakdown.
The core finding: you're at ~42% overall, but the gap is concentrated in 3 critical areas:

The "free internet" promise requires this specific chain to work end-to-end:
Android app → FastAPI → SQLite queue → pass scheduler 
→ RPi LoRa node (SX1276 @ 868 MHz) 
→ FOSSASAT-2E overhead pass 
→ FOSSA ground station downlink 
→ FOSSA cloud API → /inbox delivery
Right now, the middle chunk — pass scheduler, RPi hardware driver, and Doppler correction — is the missing link. Everything else either exists or is straightforward to build.
The most honest constraint is still the one in your own README: 577 bps, 36 sec/hour shared TX time, 10–20 users per node. "Free internet" for OpenOrbitLink really means free async satellite messaging — not browsing. That's worth communicating clearly to users before they try it, or you'll get frustrated users expecting WhatsApp and getting a 3-hour delayed text.
Cheapest way to prove it works: buy a Raspberry Pi Zero 2W (~₹1,800) + RA-02 LoRa module (~₹600) + wire antenna (~₹200), flash the ground station daemon, and send one message to FOSSASAT-2E. That single successful round-trip validates the whole architecture.Sonnet 4.6AdaptiveClaude is AI