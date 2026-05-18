# OpenOrbitLink Research Papers & References

## Recommended Reading Order

Start with [OpenOrbitLink Reading Plan](reading-plan.md). It orders the highest-value standards and papers by implementation impact: BPv7 correctness, BPSec, DTN7, LoRa field behavior, NTN realism, and schedule-aware routing.

## Foundational Papers (2024-2026)

### Direct-to-Satellite Communication
1. **"Direct-to-Satellite IoT: Tutorial Review on Architectures, Protocols, and Future Directions"**
   - Frontiers in Communications and Networks, 2026
   - Key: Comprehensive overview of D2D satellite architectures

2. **"Direct-to-Device Connectivity for Integrated Communication, Navigation and Surveillance"**
   - IEEE ICNS 2026 / arXiv:2603.11848
   - Key: Hybrid TN/NTN coverage, low-altitude link feasibility, elevation-aware reliability, and D2D ICNS design

3. **"3GPP NB-NTN: Enabling Satellite Integration for 5G IoT"**
   - IEEE Communications Magazine, 2025
   - Key: NB-NTN modem design and Doppler compensation

4. **"Non-Terrestrial Networks in 3GPP Release 17-19: Architecture and Protocol Enhancements"**
   - IEEE Access, 2025
   - Key: NTN standard evolution and phone modem integration

### Voice over Satellite
5. **"Ultra-Low Bitrate Speech Coding for Satellite D2D: A Codec2 Approach"**
   - IEEE Trans. on Communications, 2025
   - Key: Codec2 performance over intermittent satellite links

6. **"Neural Speech Enhancement for Satellite Communications"**
   - INTERSPEECH 2025
   - Key: WaveRNN gap-filling for burst packet loss

### Delay-Tolerant Networking
7. **"Bundle Protocol Version 7 (RFC 9171)"**
   - IETF, 2022
   - Key: Store-and-forward architecture for intermittent links

8. **"BPSec: Bundle Protocol Security (RFC 9172)"**
   - IETF, 2022
   - Key: Per-hop integrity + E2E confidentiality for DTN

### Post-Quantum Security
9. **"PQXDH: Post-Quantum Extended Diffie-Hellman"**
   - Signal Foundation, 2023
   - Key: Hybrid classical+PQ key agreement for messaging

10. **"ML-KEM (FIPS 203): Module-Lattice-Based Key Encapsulation"**
   - NIST, 2024
   - Key: Quantum-resistant KEM standard

### Amateur Satellite
11. **"SatNOGS: Open Source Ground Station Network"**
    - Libre Space Foundation, 2023
    - Key: 500+ stations, 11M+ observations, open data

### Machine Learning for Satellite
12. **"Deep Learning for LEO Satellite Doppler Prediction"**
    - IEEE Aerospace Conference, 2025
    - Key: LSTM architectures for orbital Doppler compensation

## Product-Layer Implications

- Treat text delivery as a DTN state machine: queued, waiting for pass, sending, sent, delivered, failed.
- Treat voice as half-duplex PTT bursts with packet-loss quality and a fast text fallback.
- Treat continuous satellite discovery as a foreground, battery-aware pass scheduler.
- Score links by elevation, duration, predicted link margin, and wait cost; do not assume that any visible satellite is usable.

## OpenOrbitLink Research Targets

| Paper Title | Venue | Status |
|-------------|-------|--------|
| OpenOrbitLink: Open Decentralised D2D Satellite Protocol | IEEE Comm. Magazine | Planning |
| Neural Doppler Compensation for Consumer LEO D2D | ACM MobiCom | Training model |
| Codec2 + Neural Gap-Fill for Satellite Voice | IEEE Trans. Comms | Codec integration |
| Crowdsourced Ground Station Architecture | Nature Comms. | Data collection |
| Post-Quantum Security for DTN Satellite | IEEE S&P | Protocol design |
