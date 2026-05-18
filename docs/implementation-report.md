# OpenOrbitLink Private Implementation Report

## Summary

OpenOrbitLink is now organized as a private-ready repository with build
scaffolding, generated protobuf bindings, Android resources, CI-facing tests,
and publishing guardrails. The repository intentionally excludes Starlink APK
and decompiled output directories.

The latest product-layer pass adds the missing user-facing communication
surfaces: inbox/chat state, PTT calling, and nearby-pass discovery.

## Labels

- `android`: Android app, Compose UI, NDK, resources, and manifest work.
- `backend`: Python ground station, relay daemon, and service runtime.
- `grpc`: Protobuf schema, generated bindings, and `grpc.aio` server work.
- `docs`: README, architecture, hardware, and setup documentation.
- `ci`: GitHub Actions, test commands, and build reproducibility.
- `security`: cryptography, key management, and privacy-sensitive changes.
- `product`: chat, calling, nearby-pass discovery, and Android UX state models.
- `priority:p0`: build blockers or runtime blockers.
- `priority:p1`: important correctness or integration fixes.
- `priority:p2`: documentation, polish, and prototype hardening.

## Description

OpenOrbitLink is an open satellite communication stack for Android devices,
LoRa relays, SDR receivers, and community ground stations. It combines a
Jetpack Compose Android prototype, Python protocol and DTN references, a Rust
packet core, RF simulations, and a protobuf-backed ground station service.
The Android app now includes a product-layer prototype for threaded messaging,
half-duplex PTT calls, and a foreground nearby-pass discovery engine.

## Current Verification

- Python syntax/import compilation is expected to run with `python -m compileall`.
- End-to-end protocol verification is expected to run with `python tests/test_e2e.py`.
- Pytest collection is supported through `python -m pytest`.
- Rust protocol tests are expected to run with `cargo test` in `protocol-rs`.
- Android debug APK builds are expected to run with `./gradlew assembleDebug`
  from the `android` directory once Android SDK and JDK are available.

## Product-Layer Additions

- `MessagingScreen`: inbox cards, unread badges, queued counts, quoted replies,
  voice-burst placeholder rows, retry action, and delivery states.
- `CallPttScreen`: half-duplex call UI with packet-loss quality, mute/speaker
  controls, burst log, and text fallback.
- `NearbyPassesScreen`: visible-now, next-pass, best-reliability cards backed by
  a shared pass scorer.
- `NearbyPassService`: foreground service skeleton for user-visible, battery-aware
  pass discovery.
- `docs/product-layer-roadmap.md`: detailed design plan for chat, PTT, and
  continuous discovery.

## Excluded From Publish

- `starlink_decompiled_jadx/`
- `starlink_decompiled_apktool/`
- `Starlink_*.apk`
