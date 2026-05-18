from __future__ import annotations

"""
OpenOrbitLink GNU Radio Flowgraph — ISS APRS Packet Decoder

Decodes AX.25 APRS packets from the International Space Station
digipeater on 144.390 MHz (Region 2) / 145.825 MHz (worldwide).

Usage:
    python -m dsp.flowgraphs.iss_aprs_decode --simulate
    python -m dsp.flowgraphs.iss_aprs_decode --freq 145.825e6

Hardware: RTL-SDR V4 + VHF antenna
License: Receive-only — no license required for RX
"""

import sys
import time
import argparse
import struct

import numpy as np

try:
    from gnuradio import gr, blocks, analog, digital, filter as gr_filter
    import osmosdr
    HAS_GNURADIO = True
except ImportError:
    HAS_GNURADIO = False


ISS_APRS_FREQ_WORLDWIDE = 145.825e6
ISS_APRS_FREQ_NA = 144.390e6
SAMPLE_RATE = 250000       # 250 ksps
BAUD_RATE = 1200           # AFSK 1200 baud
MARK_FREQ = 1200           # Mark tone
SPACE_FREQ = 2200          # Space tone


class AX25Decoder:
    """
    Simple AX.25 frame decoder for APRS packets.

    Processes demodulated audio looking for AX.25 flag bytes (0x7E)
    and extracts frames with NRZI decoding and bit-unstuffing.
    """

    FLAG = 0x7E

    def __init__(self):
        self.packets = []

    def decode_frame(self, bits):
        """Decode an AX.25 frame from a bit stream."""
        # Find flags
        frame_bits = []
        in_frame = False
        ones_count = 0

        for bit in bits:
            if bit == 1:
                ones_count += 1
            else:
                if ones_count == 5:
                    # Bit stuffing — skip this zero
                    ones_count = 0
                    continue
                elif ones_count == 6:
                    # Flag detected
                    if in_frame and len(frame_bits) >= 8:
                        frame = self._bits_to_bytes(frame_bits)
                        if frame and len(frame) >= 14:
                            self.packets.append(frame)
                    frame_bits = []
                    in_frame = True
                    ones_count = 0
                    continue
                elif ones_count >= 7:
                    # Abort
                    in_frame = False
                    frame_bits = []
                    ones_count = 0
                    continue
                ones_count = 0

            if in_frame:
                frame_bits.append(bit)

    def _bits_to_bytes(self, bits):
        """Convert bit list to bytes (LSB first per AX.25)."""
        result = bytearray()
        for i in range(0, len(bits) - 7, 8):
            byte = 0
            for j in range(8):
                byte |= bits[i + j] << j  # LSB first
            result.append(byte)
        return bytes(result)

    def parse_aprs(self, frame):
        """Parse an AX.25 APRS frame into human-readable format."""
        if len(frame) < 16:
            return None

        # Extract addresses (7 bytes each, shifted left by 1)
        dest_raw = frame[0:6]
        src_raw = frame[7:13]

        dest = ''.join(chr(b >> 1) for b in dest_raw).strip()
        src = ''.join(chr(b >> 1) for b in src_raw).strip()

        # Skip digipeater addresses
        info_start = 14
        i = 13
        while i < len(frame) and not (frame[i] & 0x01):
            i += 7
            info_start = i + 1

        # Control + PID
        if info_start + 2 > len(frame):
            return None

        info = frame[info_start + 2:]  # Skip control + PID

        return {
            "source": src,
            "destination": dest,
            "info": info.decode('ascii', errors='replace'),
        }


class IssAprsDecoder:
    """
    ISS APRS Packet Decoder.

    Flowgraph:
        RTL-SDR Source (145.825 MHz, 250 ksps)
        → AGC
        → AFSK Demodulator (Bell 202: 1200/2200 Hz)
        → Clock Recovery
        → AX.25 Decoder
        → APRS Parser
    """

    def __init__(self, frequency=ISS_APRS_FREQ_WORLDWIDE, output_file="iss_packets.log"):
        self.frequency = frequency
        self.output_file = output_file
        self.decoder = AX25Decoder()

    def simulate(self, n_packets=5):
        """Generate synthetic APRS packets for testing."""
        print("=" * 60)
        print(f"ISS APRS Decoder — Simulation Mode")
        print(f"Generating {n_packets} synthetic APRS packets")
        print("=" * 60)

        # Simulate some realistic ISS APRS packets
        test_packets = [
            {"src": "RS0ISS", "dest": "CQ", "info": ">ARISS - International Space Station"},
            {"src": "RS0ISS", "dest": "CQ", "info": "!4851.50N/00220.50E-PHG5760/ISS APRS Digi"},
            {"src": "W3ADO", "dest": "RS0ISS", "info": ":BLN1     :OpenOrbitLink test message via ISS"},
            {"src": "VU2ASH", "dest": "RS0ISS", "info": "=2836.83N/07712.54E-OpenOrbitLink Ground Station Delhi"},
            {"src": "RS0ISS", "dest": "CQ", "info": "T#001,100,050,075,025,050,00000000"},
        ]

        decoded = []
        for i, pkt in enumerate(test_packets[:n_packets]):
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            result = {
                "timestamp": timestamp,
                "source": pkt["src"],
                "destination": pkt["dest"],
                "info": pkt["info"],
                "rssi_dbm": -75 + np.random.randint(-20, 10),
            }
            decoded.append(result)
            print(f"  [{timestamp}] {pkt['src']}>{pkt['dest']}: {pkt['info']}")

        # Save to log
        with open(self.output_file, 'w') as f:
            for d in decoded:
                f.write(f"{d['timestamp']} | {d['source']}>{d['destination']} | "
                        f"RSSI:{d['rssi_dbm']}dBm | {d['info']}\n")

        print(f"\n{len(decoded)} packets saved to {self.output_file}")
        return decoded

    def run_gnuradio(self, duration_seconds=600):
        """Run live ISS APRS decoding via GNU Radio."""
        if not HAS_GNURADIO:
            print("ERROR: GNU Radio not installed.")
            return False

        print("=" * 60)
        print(f"ISS APRS Decoder — Live Mode")
        print(f"Frequency: {self.frequency/1e6:.3f} MHz")
        print(f"Duration: {duration_seconds}s")
        print("Listening for ISS APRS packets...")
        print("=" * 60)

        # In production: full GNU Radio flowgraph with AFSK demod
        # For now: placeholder
        print("GNU Radio live decoding not yet implemented.")
        print("Use --simulate for testing.")
        return False


def main():
    parser = argparse.ArgumentParser(description="ISS APRS Packet Decoder")
    parser.add_argument("--freq", type=float, default=ISS_APRS_FREQ_WORLDWIDE)
    parser.add_argument("--output", type=str, default="iss_packets.log")
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--packets", type=int, default=5)
    args = parser.parse_args()

    decoder = IssAprsDecoder(frequency=args.freq, output_file=args.output)

    if args.simulate:
        decoder.simulate(args.packets)
    else:
        decoder.run_gnuradio(args.duration)


if __name__ == "__main__":
    main()
