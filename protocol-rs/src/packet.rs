//! FreeSat Packet — Wire format encoding and decoding
//!
//! Packet structure:
//! ```text
//! ┌──────┬───────┬─────┬──────┬─────────┬─────┬──────┐
//! │ SYNC │DEV_ID │TIME │ TYPE │ PAYLOAD │ FEC │ CRC  │
//! │4 byte│6 byte │4 by │1 by  │variable │32 by│2 byte│
//! └──────┴───────┴─────┴──────┴─────────┴─────┴──────┘
//! ```

use sha2::{Sha256, Digest};
use serde::{Serialize, Deserialize};

/// Sync word: 0xFE6B2840 (Barker-13 inspired)
pub const SYNC_WORD: [u8; 4] = [0xFE, 0x6B, 0x28, 0x40];

/// CRC-16 CCITT polynomial
const CRC_POLY: u16 = 0x1021;

/// Maximum payload size in bytes
pub const MAX_PAYLOAD_SIZE: usize = 2048;

/// FEC parity size (Reed-Solomon)
pub const FEC_SIZE: usize = 32;

/// Minimum packet size (header + FEC + CRC, no payload)
pub const MIN_PACKET_SIZE: usize = 4 + 6 + 4 + 1 + 1 + 1 + 2 + FEC_SIZE + 2;

/// Payload type codes
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum PayloadType {
    Text = 0x01,
    Voice = 0x02,
    Sos = 0x03,
    Relay = 0x04,
    Ack = 0x05,
    Beacon = 0x06,
}

impl PayloadType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0x01 => Some(Self::Text),
            0x02 => Some(Self::Voice),
            0x03 => Some(Self::Sos),
            0x04 => Some(Self::Relay),
            0x05 => Some(Self::Ack),
            0x06 => Some(Self::Beacon),
            _ => None,
        }
    }

    /// Maximum TTL in seconds for this payload type
    pub fn default_ttl_seconds(&self) -> u32 {
        match self {
            Self::Sos => 0,        // Never expires
            Self::Voice => 3600,   // 1 hour
            Self::Text => 86400,   // 24 hours
            Self::Relay => 86400,
            Self::Ack => 7200,     // 2 hours
            Self::Beacon => 600,   // 10 minutes
        }
    }

    /// Priority level (0 = highest)
    pub fn priority(&self) -> u8 {
        match self {
            Self::Sos => 0,
            Self::Ack => 1,
            Self::Voice => 1,
            Self::Text => 2,
            Self::Relay => 3,
            Self::Beacon => 4,
        }
    }
}

/// FreeSat protocol packet
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FreeSatPacket {
    pub device_id: [u8; 6],
    pub timestamp: u32,
    pub payload_type: PayloadType,
    pub hop_count: u8,
    pub ttl: u8,
    pub payload: Vec<u8>,
    pub fec_data: Vec<u8>,
}

impl FreeSatPacket {
    /// Create a new packet
    pub fn new(device_id: [u8; 6], payload_type: PayloadType, payload: Vec<u8>) -> Self {
        assert!(
            payload.len() <= MAX_PAYLOAD_SIZE,
            "payload exceeds MAX_PAYLOAD_SIZE"
        );
        let fec = compute_xor_parity(&payload, FEC_SIZE);
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as u32;

        Self {
            device_id,
            timestamp: now,
            payload_type,
            hop_count: 0,
            ttl: 10,
            payload,
            fec_data: fec,
        }
    }

    /// True when the packet must not be relayed again.
    pub fn hop_limit_exceeded(&self) -> bool {
        self.hop_count >= self.ttl
    }

    /// Return a packet copy prepared for the next relay hop.
    pub fn relay_copy(&self) -> Result<Self, &'static str> {
        if self.hop_limit_exceeded() {
            return Err("packet hop limit exceeded");
        }
        let mut copy = self.clone();
        copy.hop_count += 1;
        Ok(copy)
    }

    /// Generate device ID from a unique string
    pub fn generate_device_id(unique_str: &str) -> [u8; 6] {
        let hash = Sha256::digest(unique_str.as_bytes());
        let mut id = [0u8; 6];
        id.copy_from_slice(&hash[..6]);
        id
    }

    /// Serialize packet to wire format bytes
    pub fn serialize(&self) -> Vec<u8> {
        assert!(
            self.payload.len() <= MAX_PAYLOAD_SIZE,
            "payload exceeds MAX_PAYLOAD_SIZE"
        );
        let payload_len = self.payload.len() as u16;
        let mut buf = Vec::with_capacity(MIN_PACKET_SIZE + self.payload.len());

        // Sync word
        buf.extend_from_slice(&SYNC_WORD);
        // Device ID
        buf.extend_from_slice(&self.device_id);
        // Timestamp (big-endian)
        buf.extend_from_slice(&self.timestamp.to_be_bytes());
        // Payload type
        buf.push(self.payload_type as u8);
        // Hop count
        buf.push(self.hop_count);
        // TTL
        buf.push(self.ttl);
        // Payload length (big-endian)
        buf.extend_from_slice(&payload_len.to_be_bytes());
        // Payload
        buf.extend_from_slice(&self.payload);
        // FEC (padded to 32 bytes)
        let mut fec = self.fec_data.clone();
        fec.resize(FEC_SIZE, 0);
        buf.extend_from_slice(&fec);

        // CRC-16 over everything
        let crc = crc16_ccitt(&buf);
        buf.extend_from_slice(&crc.to_be_bytes());

        buf
    }

    /// Deserialize packet from wire format bytes
    pub fn deserialize(data: &[u8]) -> Option<Self> {
        if data.len() < MIN_PACKET_SIZE {
            return None;
        }

        // Check sync word
        if data[0..4] != SYNC_WORD {
            return None;
        }

        // Verify CRC
        let crc_offset = data.len() - 2;
        let expected_crc = u16::from_be_bytes([data[crc_offset], data[crc_offset + 1]]);
        let actual_crc = crc16_ccitt(&data[..crc_offset]);
        if expected_crc != actual_crc {
            return None;
        }

        // Parse header
        let mut device_id = [0u8; 6];
        device_id.copy_from_slice(&data[4..10]);

        let timestamp = u32::from_be_bytes([data[10], data[11], data[12], data[13]]);
        let payload_type = PayloadType::from_u8(data[14])?;
        let hop_count = data[15];
        let ttl = data[16];
        let payload_len = u16::from_be_bytes([data[17], data[18]]) as usize;
        if payload_len > MAX_PAYLOAD_SIZE {
            return None;
        }

        let expected_len = 19 + payload_len + FEC_SIZE + 2;
        if data.len() != expected_len {
            return None;
        }

        // Bounds check
        if 19 + payload_len + FEC_SIZE + 2 > data.len() {
            return None;
        }

        let payload = data[19..19 + payload_len].to_vec();
        let fec_start = 19 + payload_len;
        let fec_data = data[fec_start..fec_start + FEC_SIZE].to_vec();

        Some(Self {
            device_id,
            timestamp,
            payload_type,
            hop_count,
            ttl,
            payload,
            fec_data,
        })
    }
}

/// CRC-16 CCITT checksum
pub fn crc16_ccitt(data: &[u8]) -> u16 {
    let mut crc: u16 = 0xFFFF;
    for &byte in data {
        crc ^= (byte as u16) << 8;
        for _ in 0..8 {
            if crc & 0x8000 != 0 {
                crc = (crc << 1) ^ CRC_POLY;
            } else {
                crc <<= 1;
            }
            crc &= 0xFFFF;
        }
    }
    crc
}

/// Compute XOR-based parity (simplified Reed-Solomon stand-in)
fn compute_xor_parity(data: &[u8], n_parity: usize) -> Vec<u8> {
    let mut parity = vec![0u8; n_parity];
    for (i, &b) in data.iter().enumerate() {
        parity[i % n_parity] ^= b;
    }
    parity
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_packet_roundtrip() {
        let id = FreeSatPacket::generate_device_id("test-device");
        let pkt = FreeSatPacket::new(id, PayloadType::Text, b"Hello FreeSat!".to_vec());
        let raw = pkt.serialize();
        let parsed = FreeSatPacket::deserialize(&raw).unwrap();

        assert_eq!(parsed.payload, b"Hello FreeSat!");
        assert_eq!(parsed.device_id, id);
        assert_eq!(parsed.payload_type, PayloadType::Text);
    }

    #[test]
    fn test_crc_corruption_detection() {
        let id = FreeSatPacket::generate_device_id("test");
        let pkt = FreeSatPacket::new(id, PayloadType::Beacon, vec![1, 2, 3]);
        let mut raw = pkt.serialize();
        // Corrupt last byte
        let last = raw.len() - 1;
        raw[last] ^= 0xFF;
        assert!(FreeSatPacket::deserialize(&raw).is_none());
    }

    #[test]
    fn test_sos_packet() {
        let id = FreeSatPacket::generate_device_id("emergency");
        let payload = b"28.6139,77.2090,HELP".to_vec();
        let pkt = FreeSatPacket::new(id, PayloadType::Sos, payload.clone());
        let raw = pkt.serialize();
        let parsed = FreeSatPacket::deserialize(&raw).unwrap();

        assert_eq!(parsed.payload_type, PayloadType::Sos);
        assert_eq!(parsed.payload, payload);
        assert_eq!(parsed.payload_type.priority(), 0);
    }

    #[test]
    fn test_crc16() {
        let data = b"FreeSat";
        let crc = crc16_ccitt(data);
        assert_ne!(crc, 0);
        // Same input should give same CRC
        assert_eq!(crc, crc16_ccitt(data));
    }

    #[test]
    fn test_device_id_deterministic() {
        let id1 = FreeSatPacket::generate_device_id("abc");
        let id2 = FreeSatPacket::generate_device_id("abc");
        let id3 = FreeSatPacket::generate_device_id("xyz");
        assert_eq!(id1, id2);
        assert_ne!(id1, id3);
    }

    #[test]
    fn test_rejects_trailing_bytes() {
        let id = FreeSatPacket::generate_device_id("strict");
        let pkt = FreeSatPacket::new(id, PayloadType::Text, b"strict".to_vec());
        let mut raw = pkt.serialize();
        raw.push(0);
        assert!(FreeSatPacket::deserialize(&raw).is_none());
    }

    #[test]
    fn test_relay_copy_enforces_hop_limit() {
        let id = FreeSatPacket::generate_device_id("relay");
        let mut pkt = FreeSatPacket::new(id, PayloadType::Relay, b"x".to_vec());
        pkt.hop_count = 9;
        pkt.ttl = 10;
        let relayed = pkt.relay_copy().unwrap();
        assert_eq!(relayed.hop_count, 10);
        assert!(relayed.relay_copy().is_err());
    }
}
