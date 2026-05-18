//! FreeSat Protocol — Rust Core Implementation
//!
//! High-performance packet encoding/decoding, CRC-16, and FEC
//! for the FreeSat satellite communication protocol.
//!
//! This library is compiled to a shared library (.so) for Android
//! via JNI, providing 10-50x speedup over the Python reference.

pub mod packet;

pub use packet::{FreeSatPacket, PayloadType, crc16_ccitt};
