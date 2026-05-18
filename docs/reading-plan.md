# OpenOrbitLink Reading Plan

## Summary

This reading plan prioritizes papers and standards that directly improve OpenOrbitLink's weakest current areas: RF validation, real DTN delivery, LoRa field behavior, NTN realism, and production-grade security.

Do not start with generic AI papers. Read the material below in order, and convert each week into one implementation artifact: a test, protocol decision, field checklist, or demo requirement.

## Priority Stack

| Priority | Source | Focus | Implementation output |
|:---:|:---|:---|:---|
| 1 | [RFC 9171: Bundle Protocol Version 7](https://www.rfc-editor.org/rfc/rfc9171.html) | Sections 3, 4, 5, 6, 7, Appendix B | BPv7 bundle model, lifecycle states, endpoint IDs, status reports |
| 2 | [RFC 9172: Bundle Protocol Security](https://www.rfc-editor.org/rfc/rfc9172.html) | BIB, BCB, security policy, reason codes | BPSec threat model and block-level security plan |
| 3 | [DTN7: Open-Source BPv7 Implementation](https://arxiv.org/abs/1908.10237) | Real BPv7 architecture and implementation tradeoffs | Comparison notes against OpenOrbitLink DTN engine |
| 4 | [LoRAgent: DTN-Based Communication Using LoRa](https://carsec.net/bib/baumgaertner2020loragent/baumgaertner2020loragent.pdf) | LoRa + DTN disaster messaging | LoRa relay assumptions, payload limits, and field-test checklist |
| 5 | [LoRa-Based Smartphone Communication for Crisis Scenarios](https://idl.iscram.org/files/jonashochst/2020/2291_JonasHochst_etal2020.pdf) | Smartphone-to-LoRa crisis communication | Android + LoRa UX and pairing requirements |
| 6 | [3GPP NTN Overview](https://www.3gpp.org/technologies/ntn-overview) | Release 17-19 NTN path | NTN requirements map: timing advance, Doppler, GNSS, ephemeris, discontinuous coverage |
| 7 | [Direct-to-Device Connectivity for ICNS](https://arxiv.org/abs/2603.11848) | Hybrid TN/NTN reliability and elevation-aware scoring | Update pass scoring inputs and link reliability language |
| 8 | [5G NR NTN: From Early Results to the Road Ahead](https://arxiv.org/abs/2601.04882) | NR-NTN standards and simulation results | NTN realism checklist for future simulator work |
| 9 | [D2C vs 3GPP NTN for Global Connectivity](https://arxiv.org/abs/2605.05843) | Direct-to-cell versus standardized NTN | Positioning note: what OpenOrbitLink is and is not competing with |
| 10 | [CCSDS Schedule-Aware Bundle Routing](https://ccsds.org/publications/allpubs/entry/3167/) | Contact-window-aware routing | Contact plan design for satellite pass scheduling |

## Six-Week Reading Order

| Week | Read | Engineering deliverable |
|:---:|:---|:---|
| 1 | RFC 9171 + DTN7 | BPv7 gap list for `protocol/dtn.py` and `protocol-rs` |
| 2 | RFC 9172 | BPSec policy note for payload confidentiality, integrity, replay, and failed security operations |
| 3 | LoRAgent + LoRa smartphone crisis paper | LoRa relay field-test checklist and Android pairing requirements |
| 4 | 3GPP NTN overview + D2D ICNS paper | NTN link scoring update: elevation, duration, SNR margin, GNSS/ephemeris assumptions |
| 5 | NR-NTN road-ahead + D2C vs NTN comparison | Strategy note separating amateur/DTN paths from commercial NTN/D2C |
| 6 | CCSDS schedule-aware routing | Contact-plan model for pass windows, queued bundles, and route selection |

## Implementation Notes

- **DTN correctness first**: align internal bundle lifecycle with BPv7 concepts before adding more UI states.
- **BPSec second**: define what is protected at the bundle layer versus what remains application-level encryption.
- **RF and LoRa proof third**: each paper should produce a measurable field-test target, not only a citation.
- **NTN realism fourth**: use 3GPP material to avoid unrealistic direct-to-cell claims and to model timing, Doppler, and discontinuous coverage.
- **AI later**: keep AI focused on pass scoring, Doppler prediction, packet loss recovery, and adaptive routing after the RF/DTN base is credible.

## Acceptance Criteria

- `docs/research-papers.md` links to this plan as the recommended reading order.
- README research section points readers to this plan instead of listing only generic paper targets.
- Each listed source has a clear implementation output tied to OpenOrbitLink's roadmap.
