"""
OpenOrbitLink — Voice Codec Benchmark Suite

Comprehensive benchmarking framework for the hybrid voice codec stack:
  - Bitrate measurement per codec mode
  - Chunking overhead analysis
  - LoRa airtime calculation validation
  - Packet loss impact simulation (Gilbert-Elliott model)
  - Quality estimation (energy correlation proxy)
  - Voice message sizing for different durations
"""

import os
import sys
import time
import math
import argparse
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.voice_transport import (
    VoiceCodecMode, VoiceChunk, CODEC_PROPERTIES,
    chunk_voice_message, frames_per_chunk,
    estimate_lora_airtime, fits_duty_cycle,
    VoiceReassemblyBuffer,
)


# ── Benchmark Results ────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    test_name: str
    codec_mode: str
    duration_s: float = 0.0
    total_frames: int = 0
    total_bytes: int = 0
    total_chunks: int = 0
    bytes_per_second: float = 0.0
    overhead_percent: float = 0.0
    lora_airtime_s: float = 0.0
    fits_duty_cycle: bool = False
    chunk_efficiency: float = 0.0  # payload/total ratio
    extra: dict = field(default_factory=dict)

    def __str__(self):
        return (f"  {self.test_name}: {self.codec_mode}\n"
                f"    Duration: {self.duration_s:.1f}s | Frames: {self.total_frames}\n"
                f"    Data: {self.total_bytes} bytes | Chunks: {self.total_chunks}\n"
                f"    Rate: {self.bytes_per_second:.0f} B/s | "
                f"Overhead: {self.overhead_percent:.1f}%\n"
                f"    LoRa airtime: {self.lora_airtime_s:.1f}s | "
                f"Duty OK: {'✓' if self.fits_duty_cycle else '✗'}")


# ── Benchmark Functions ──────────────────────────────────────────────────────

def benchmark_codec_sizing():
    """Measure frame and chunk sizes for all codec modes."""
    print("\n" + "="*72)
    print("  CODEC SIZING BENCHMARK")
    print("="*72)

    durations = [5, 10, 30]  # seconds

    for mode in VoiceCodecMode:
        props = CODEC_PROPERTIES[mode]
        print(f"\n{'─'*40}")
        print(f"  {mode.name}: {props['bitrate']} bps, "
              f"{props['frame_ms']}ms frames, "
              f"{props['frame_bytes']} bytes/frame")
        print(f"  LoRa-safe: {'✓' if props['lora_safe'] else '✗'} | "
              f"Frames/chunk: {frames_per_chunk(mode)}")

        for dur in durations:
            num_frames = (dur * 1000) // props["frame_ms"]
            frames = [os.urandom(props["frame_bytes"]) for _ in range(num_frames)]
            meta, chunks = chunk_voice_message(frames, mode)

            raw_bytes = num_frames * props["frame_bytes"]
            wire_bytes = sum(c.wire_size for c in chunks)
            overhead = ((wire_bytes - raw_bytes) / raw_bytes * 100) if raw_bytes > 0 else 0

            airtime = estimate_lora_airtime(len(chunks), 80)
            fits = fits_duty_cycle(len(chunks), 80)

            result = BenchmarkResult(
                test_name=f"{dur}s message",
                codec_mode=mode.name,
                duration_s=dur,
                total_frames=num_frames,
                total_bytes=raw_bytes,
                total_chunks=len(chunks),
                bytes_per_second=raw_bytes / dur,
                overhead_percent=overhead,
                lora_airtime_s=airtime,
                fits_duty_cycle=fits,
            )
            print(result)


def benchmark_packet_loss():
    """Simulate Gilbert-Elliott packet loss model and measure impact."""
    print("\n" + "="*72)
    print("  PACKET LOSS SIMULATION (Gilbert-Elliott Model)")
    print("="*72)

    # Gilbert-Elliott parameters for LoRa ISM channels
    scenarios = [
        ("Good channel",    0.01, 0.90),  # Low loss, fast recovery
        ("Urban ISM",       0.10, 0.70),  # Moderate loss
        ("Dense IoT",       0.20, 0.50),  # High contention
        ("Hostile RF",      0.40, 0.30),  # Extreme conditions
    ]

    mode = VoiceCodecMode.CODEC2_700C
    num_frames = 125  # 5s message

    for name, p_loss, p_recover in scenarios:
        frames = [os.urandom(4) for _ in range(num_frames)]
        meta, chunks = chunk_voice_message(frames, mode, message_id=42)

        # Simulate Gilbert-Elliott loss
        in_burst = False
        delivered = 0
        lost = 0
        reassembly = VoiceReassemblyBuffer(42)

        for chunk in chunks:
            if in_burst:
                # In burst loss state
                if hash(chunk.sequence_num) % 100 < int(p_recover * 100):
                    in_burst = False
            else:
                # In good state
                if hash(chunk.sequence_num * 7) % 100 < int(p_loss * 100):
                    in_burst = True

            if not in_burst:
                wire = chunk.serialize()
                parsed = VoiceChunk.deserialize(wire)
                reassembly.add_chunk(parsed)
                delivered += 1
            else:
                lost += 1

        stats = reassembly.get_stats()
        actual_loss = lost / len(chunks) * 100 if chunks else 0

        print(f"\n  {name}: p_loss={p_loss:.2f}, p_recover={p_recover:.2f}")
        print(f"    Delivered: {delivered}/{len(chunks)} chunks "
              f"({actual_loss:.0f}% loss)")
        print(f"    Complete: {'✓' if stats['is_complete'] else '✗'} | "
              f"Missing: {stats['missing'][:5]}{'...' if len(stats['missing']) > 5 else ''}")


def benchmark_airtime_matrix():
    """Airtime matrix for all codec modes and message durations."""
    print("\n" + "="*72)
    print("  LORA AIRTIME MATRIX (seconds at 577 bps effective)")
    print("="*72)

    durations = [1, 2, 5, 10, 30]
    lora_safe_modes = [m for m in VoiceCodecMode if CODEC_PROPERTIES[m]["lora_safe"]]

    # Header
    header = f"{'Mode':<15}"
    for d in durations:
        header += f"{'  ' + str(d) + 's':>8}"
    header += "   Budget"
    print(f"\n  {header}")
    print(f"  {'─'*65}")

    for mode in lora_safe_modes:
        props = CODEC_PROPERTIES[mode]
        row = f"  {mode.name:<15}"

        for dur in durations:
            num_frames = (dur * 1000) // props["frame_ms"]
            frames = [b'\x00' * props["frame_bytes"]] * num_frames
            meta, chunks = chunk_voice_message(frames, mode)
            airtime = estimate_lora_airtime(len(chunks), 80)
            fits = "✓" if airtime <= 36.0 else "✗"
            row += f"  {airtime:5.1f}s{fits}"

        row += f"   36.0s"
        print(row)


def benchmark_chunk_efficiency():
    """Measure payload efficiency (useful bytes / wire bytes)."""
    print("\n" + "="*72)
    print("  CHUNK PAYLOAD EFFICIENCY")
    print("="*72)

    print(f"\n  {'Mode':<15} {'Bytes/frame':>11} {'Frames/chunk':>13} "
          f"{'Payload':>8} {'Wire':>6} {'Efficiency':>10}")
    print(f"  {'─'*65}")

    for mode in VoiceCodecMode:
        props = CODEC_PROPERTIES[mode]
        fpc = frames_per_chunk(mode)
        payload = fpc * props["frame_bytes"]
        wire = payload + 10  # 10-byte header

        efficiency = (payload / wire * 100) if wire > 0 else 0

        print(f"  {mode.name:<15} {props['frame_bytes']:>11} {fpc:>13} "
              f"{payload:>6}B {wire:>5}B {efficiency:>8.1f}%")


def benchmark_voice_message_table():
    """Summary table: voice message characteristics for Codec2 700C."""
    print("\n" + "="*72)
    print("  VOICE MESSAGE SUMMARY — Codec2 700C")
    print("="*72)

    print(f"\n  {'Duration':>8} {'Frames':>7} {'Data':>7} {'Chunks':>7} "
          f"{'Airtime':>8} {'Budget':>8} {'Status':>7}")
    print(f"  {'─'*56}")

    for dur in [1, 2, 3, 5, 10, 15, 20, 30]:
        num_frames = (dur * 1000) // 40
        data_bytes = num_frames * 4
        frames = [b'\x00' * 4] * num_frames
        meta, chunks = chunk_voice_message(
            frames, VoiceCodecMode.CODEC2_700C)
        airtime = estimate_lora_airtime(len(chunks), 80)
        fits = fits_duty_cycle(len(chunks), 80)

        print(f"  {dur:>6}s {num_frames:>7} {data_bytes:>5}B {len(chunks):>7} "
              f"{airtime:>6.1f}s {36.0:>6.1f}s {'  ✓' if fits else '  ✗'}")


# ── Main ─────────────────────────────────────────────────────────────────────

def run_all_benchmarks():
    """Run all benchmark suites."""
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  OpenOrbitLink — Hybrid Voice Codec Benchmark Suite  ║")
    print("╚══════════════════════════════════════════════════════╝")

    start = time.time()

    benchmark_codec_sizing()
    benchmark_chunk_efficiency()
    benchmark_airtime_matrix()
    benchmark_voice_message_table()
    benchmark_packet_loss()

    elapsed = time.time() - start
    print(f"\n{'='*72}")
    print(f"  All benchmarks completed in {elapsed:.2f}s")
    print(f"{'='*72}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="OpenOrbitLink Voice Codec Benchmarks")
    parser.add_argument('--all', action='store_true',
                        help='Run all benchmarks')
    parser.add_argument('--sizing', action='store_true',
                        help='Codec sizing benchmark')
    parser.add_argument('--efficiency', action='store_true',
                        help='Chunk efficiency benchmark')
    parser.add_argument('--airtime', action='store_true',
                        help='Airtime matrix benchmark')
    parser.add_argument('--loss', action='store_true',
                        help='Packet loss simulation')
    parser.add_argument('--summary', action='store_true',
                        help='Voice message summary table')

    args = parser.parse_args()

    if args.all or not any([args.sizing, args.efficiency, args.airtime,
                            args.loss, args.summary]):
        run_all_benchmarks()
    else:
        if args.sizing:
            benchmark_codec_sizing()
        if args.efficiency:
            benchmark_chunk_efficiency()
        if args.airtime:
            benchmark_airtime_matrix()
        if args.loss:
            benchmark_packet_loss()
        if args.summary:
            benchmark_voice_message_table()
