# OpenOrbitLink Private Implementation Report

## Summary

OpenOrbitLink is now organized as a private-ready repository with build
scaffolding, generated protobuf bindings, Android resources, CI-facing tests,
and publishing guardrails. The repository intentionally excludes Starlink APK
and decompiled output directories.

## Labels

- `android`: Android app, Compose UI, NDK, resources, and manifest work.
- `backend`: Python ground station, relay daemon, and service runtime.
- `grpc`: Protobuf schema, generated bindings, and `grpc.aio` server work.
- `docs`: README, architecture, hardware, and setup documentation.
- `ci`: GitHub Actions, test commands, and build reproducibility.
- `security`: cryptography, key management, and privacy-sensitive changes.
- `priority:p0`: build blockers or runtime blockers.
- `priority:p1`: important correctness or integration fixes.
- `priority:p2`: documentation, polish, and prototype hardening.

## Description

OpenOrbitLink is an open satellite communication stack for Android devices,
LoRa relays, SDR receivers, and community ground stations. It combines a
Jetpack Compose Android prototype, Python protocol and DTN references, a Rust
packet core, RF simulations, and a protobuf-backed ground station service.

## Current Verification

- Python syntax/import compilation is expected to run with `python -m compileall`.
- End-to-end protocol verification is expected to run with `python tests/test_e2e.py`.
- Pytest collection is supported through `python -m pytest`.
- Rust protocol tests are expected to run with `cargo test` in `protocol-rs`.
- Android debug APK builds are expected to run with `./gradlew assembleDebug`
  from the `android` directory once Android SDK and JDK are available.

## Excluded From Publish

- `starlink_decompiled_jadx/`
- `starlink_decompiled_apktool/`
- `Starlink_*.apk`
