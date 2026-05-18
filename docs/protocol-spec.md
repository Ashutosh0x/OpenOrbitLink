# OpenOrbitLink Protocol Specification

## Packet Wire Format

All integer fields are big-endian.

| Offset | Size | Field | Description |
|:---:|:---:|:---|:---|
| 0 | 4 | `SYNC` | `0xFE6B2840` sync word. |
| 4 | 6 | `DEVICE_ID` | SHA-256 truncated device identifier. |
| 10 | 4 | `TIMESTAMP` | Unix UTC seconds. |
| 14 | 1 | `PAYLOAD_TYPE` | Text, voice, SOS, relay, ACK, beacon. |
| 15 | 1 | `TRANSMIT_BAND` | Unknown, amateur, ISM, licensed, NTN, receive-only. |
| 16 | 1 | `FLAGS` | Bit 0 means payload is encrypted. |
| 17 | 1 | `HOP_COUNT` | Relay hops traversed. |
| 18 | 1 | `TTL` | Maximum relay hops. |
| 19 | 2 | `PAYLOAD_LEN` | Payload bytes. |
| 21 | N | `PAYLOAD` | Plaintext or ciphertext according to band policy. |
| 21+N | 32 | `FEC` | Current prototype parity field. |
| 53+N | 2 | `CRC` | CRC-16 CCITT over header, payload, and FEC. |

## Payload Types

| Code | Name | Max Size | Default TTL | Priority |
|:---:|:---|:---:|:---:|:---:|
| `0x01` | TEXT | 256 B | 24 h | Normal |
| `0x02` | VOICE | 1024 B | 1 h | High |
| `0x03` | SOS | 64 B | Never | Critical |
| `0x04` | RELAY | 2048 B | 24 h | Normal |
| `0x05` | ACK | 16 B | 2 h | High |
| `0x06` | BEACON | 32 B | 10 min | Low |

## Band Awareness

| `TRANSMIT_BAND` | Value | Encryption | TX Requirements |
|:---|:---:|:---:|:---|
| UNKNOWN | 0 | Blocked | Must select a real path before TX. |
| AMATEUR | 1 | Blocked | Licensed operator, callsign, plaintext only. |
| ISM | 2 | Allowed | Country-specific ISM limits. |
| LICENSED | 3 | Allowed | Private/commercial license terms. |
| NTN | 4 | Allowed | Carrier-managed service. |
| RECEIVE_ONLY | 5 | Blocked | No TX path. |

The encrypted flag is not advisory. Packet serialization and BPSec BCB
validation fail when confidentiality is requested on amateur or receive-only
paths.

## FEC and Throughput

The Python prototype currently stores 32 parity bytes per packet. Production
RS(255,223) must account for 32 parity bytes per 223 data bytes plus any
interleaving and framing.

Example at 700 bps for a 256-byte text payload:

| Item | Bytes |
|:---|---:|
| Header | 21 |
| Payload | 256 |
| FEC field | 32 |
| CRC | 2 |
| Total | 311 |

On-air time is `311 * 8 / 700 = 3.55 s`. Effective payload throughput is about
577 bps before AX.25/LoRa framing, retries, duty-cycle limits, and pass-window
availability.

## Routing Rules

1. Reject the route if `LicenseGate` blocks the selected band.
2. Prefer direct satellite only when the node actually has a TX-capable path.
3. Prefer neighbors that can legally transmit on the selected band.
4. Fall back to ground station or relay nodes that pass the same band guard.
5. Store locally when no legal route exists.

## APRS Compatibility

APRS support means standards-shaped AX.25 UI frames. ISS APRS is not a general
encrypted chat relay and should only carry valid, plaintext APRS traffic from
licensed amateur operators.

## FOSSA/TinyGS Transport

`protocol.fossa` defines an 80-byte OpenOrbitLink application frame for
FOSSA/TinyGS-compatible LoRa paths:

| Field | Bytes |
|:---|---:|
| Magic `OOL` | 3 |
| Version | 1 |
| Payload type | 1 |
| Sequence | 2 |
| Flags | 1 |
| TTL | 1 |
| Payload | up to 69 |
| CRC | 2 |

Longer payloads are fragmented across multiple frames.
