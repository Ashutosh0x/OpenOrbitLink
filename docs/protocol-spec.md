# OpenOrbitLink Protocol Specification v1.0

## 1. Overview

The OpenOrbitLink protocol is a hybrid packet format designed for intermittent satellite 
communication. It combines the simplicity of AX.25, the reliability of CCSDS, and 
the delay-tolerance of BPv7 (RFC 9171) into a single lightweight protocol stack.

## 2. Packet Format

### Wire Format (Big-Endian)

```
Offset  Size    Field           Description
──────  ────    ─────           ───────────
0       4       SYNC            Synchronization word (0xFE6B2840)
4       6       DEVICE_ID       SHA-256 truncated device identifier
10      4       TIMESTAMP       Unix UTC seconds (32-bit)
14      1       PAYLOAD_TYPE    Message type code
15      1       HOP_COUNT       Number of relay hops traversed
16      1       TTL             Maximum allowed hops
17      2       PAYLOAD_LEN     Payload length in bytes
19      var     PAYLOAD         Encrypted payload data
19+N    32      FEC             Reed-Solomon (255,223) parity
51+N    2       CRC             CRC-16 CCITT checksum
```

### Sync Word Selection

`0xFE6B2840` chosen for:
- Low autocorrelation sidelobes (Barker-13 inspired)
- No common bit patterns in noise
- Distinct from AX.25 flag (0x7E) to avoid confusion

### Payload Types

| Code | Name    | Max Size | TTL      | Priority |
|------|---------|----------|----------|----------|
| 0x01 | TEXT    | 256 B    | 24 hours | Normal   |
| 0x02 | VOICE   | 1024 B   | 1 hour   | High     |
| 0x03 | SOS     | 64 B     | Never    | Critical |
| 0x04 | RELAY   | 2048 B   | 24 hours | Normal   |
| 0x05 | ACK     | 16 B     | 2 hours  | High     |
| 0x06 | BEACON  | 32 B     | 10 min   | Low      |

## 3. Error Correction

### Reed-Solomon RS(255,223)
- 32 parity symbols per block
- Corrects up to 16 symbol errors
- Detects up to 32 symbol errors
- Operates over GF(2^8)

### CRC-16 CCITT
- Polynomial: 0x1021
- Initial value: 0xFFFF
- Covers entire packet (header + payload + FEC)

## 4. Encryption

### Per-Message Encryption
- Algorithm: AES-256-GCM
- Key derivation: HKDF-SHA256
- Nonce: 12 bytes, unique per message
- Post-quantum: ML-KEM-768 key encapsulation

### Key Exchange
- Signal Protocol SPQR (Triple Ratchet)
- Forward secrecy via ratcheting
- Post-compromise security

## 5. Routing

### Priority Queue
```
SOS (0) > ACK (1) > VOICE (1) > TEXT (2) > RELAY (3) > BEACON (4)
```

### Mesh Relay Decision
```
IF satellite_visible AND has_tx:
    → Direct satellite upload
ELIF neighbor_has_satellite:
    → LoRa relay to neighbor
ELIF neighbor_closer_to_ground_station:
    → Multi-hop LoRa relay
ELSE:
    → Store locally, retry next pass
```

### TTL & Loop Prevention
- Each relay increments HOP_COUNT
- Packet discarded when HOP_COUNT >= TTL
- Device ID tracking prevents reprocessing

## 6. Modulation

### Physical Layer Options
| Modulation | Bitrate  | Required SNR | Use Case           |
|------------|----------|-------------|---------------------|
| BPSK       | 700 bps  | 3 dB        | Voice (Codec2)      |
| BPSK       | 1200 bps | 5 dB        | Text messaging      |
| QPSK       | 2400 bps | 7 dB        | Data transfer       |
| LoRa SF12  | 293 bps  | -20 dB      | Mesh relay (weak)   |

## 7. Compatibility

### AX.25 Interoperability
- OpenOrbitLink packets can be encapsulated in AX.25 UI frames
- Callsign field maps to DEVICE_ID
- Enables use of existing amateur infrastructure

### CCSDS Alignment
- FEC structure follows CCSDS 131.0-B-4
- Packet header compatible with CCSDS Space Packet Protocol

