from __future__ import annotations

"""
OpenOrbitLink GNU Radio Flowgraph — NOAA APT Weather Satellite Receiver

Python script equivalent of a GNU Radio Companion (.grc) flowgraph.
Receives NOAA APT weather satellite signals at 137 MHz via RTL-SDR.

Usage:
    python -m dsp.flowgraphs.noaa_apt_receive --freq 137.1e6

Hardware: RTL-SDR V4 + L-band or VHF antenna
License: Receive-only — no license required
"""

import sys
import os
import argparse
import time

import numpy as np

# Try to import GNU Radio — graceful fallback if not installed
try:
    from gnuradio import gr, blocks, analog, filter as gr_filter
    import osmosdr
    HAS_GNURADIO = True
except ImportError:
    HAS_GNURADIO = False


# ─── Flowgraph Configuration ─────────────────────────────────────────────

NOAA_SATELLITES = {
    "NOAA-15": 137.620e6,
    "NOAA-18": 137.9125e6,
    "NOAA-19": 137.100e6,
}

DEFAULT_SAMPLE_RATE = 2.4e6     # 2.4 Msps from RTL-SDR
AUDIO_SAMPLE_RATE = 11025       # APT standard audio rate
FM_DEVIATION = 25e3             # ±25 kHz FM deviation
RF_GAIN = 40.0                  # RTL-SDR RF gain (dB)


class NoaaAptReceiver:
    """
    NOAA APT Weather Satellite Receiver.

    Flowgraph:
        RTL-SDR Source (137.x MHz, 2.4 Msps)
        → Low Pass Filter (cutoff=60kHz, transition=10kHz)
        → FM Demodulator (deviation=25kHz)
        → Rational Resampler (2.4M → 11025 Hz)
        → WAV File Sink / Audio Sink

    Output: 11025 Hz WAV file containing APT signal
    """

    def __init__(self, frequency: float = 137.1e6, output_file: str = "noaa_apt.wav",
                 sample_rate: float = DEFAULT_SAMPLE_RATE, gain: float = RF_GAIN):
        self.frequency = frequency
        self.output_file = output_file
        self.sample_rate = sample_rate
        self.gain = gain

    def run_gnuradio(self, duration_seconds: float = 600):
        """Run the flowgraph using GNU Radio (requires gnuradio + osmosdr)."""
        if not HAS_GNURADIO:
            print("ERROR: GNU Radio not installed.")
            print("Install: sudo apt install gnuradio gr-osmosdr")
            return False

        tb = gr.top_block("NOAA APT Receiver")

        # Source: RTL-SDR
        source = osmosdr.source(args="rtl=0")
        source.set_sample_rate(self.sample_rate)
        source.set_center_freq(self.frequency)
        source.set_gain(self.gain)
        source.set_bandwidth(200e3)

        # Low-pass filter
        lpf_taps = gr_filter.firdes.low_pass(
            1.0, self.sample_rate, 60e3, 10e3,
            gr_filter.firdes.WIN_HAMMING
        )
        lpf = gr_filter.fir_filter_ccf(1, lpf_taps)

        # FM demodulator
        fm_demod = analog.fm_demod_cf(
            channel_rate=self.sample_rate,
            audio_decim=1,
            deviation=FM_DEVIATION,
            audio_pass=5500,
            audio_stop=6000,
            gain=1.0,
            tau=0,
        )

        # Rational resampler: 2.4M → 11025
        # GCD-based decimation
        from math import gcd
        g = gcd(int(self.sample_rate), AUDIO_SAMPLE_RATE)
        interp = AUDIO_SAMPLE_RATE // g
        decim = int(self.sample_rate) // g
        resampler = gr_filter.rational_resampler_fff(interp, decim)

        # WAV file sink
        wav_sink = blocks.wavfile_sink(
            self.output_file, 1, AUDIO_SAMPLE_RATE,
            blocks.FORMAT_WAV, blocks.FORMAT_PCM_16
        )

        # Connect flowgraph
        tb.connect(source, lpf, fm_demod, resampler, wav_sink)

        print("=" * 60)
        print(f"NOAA APT Receiver — {self.frequency/1e6:.3f} MHz")
        print(f"Sample rate: {self.sample_rate/1e6:.1f} Msps")
        print(f"Output: {self.output_file}")
        print(f"Duration: {duration_seconds}s")
        print("=" * 60)

        tb.start()
        time.sleep(duration_seconds)
        tb.stop()
        tb.wait()

        print(f"\nCapture complete: {self.output_file}")
        return True

    def simulate(self, duration_seconds: float = 10):
        """
        Simulate NOAA APT reception without hardware.
        Generates a synthetic APT-like signal for testing the decode pipeline.
        """
        print("=" * 60)
        print(f"NOAA APT Simulation — {self.frequency/1e6:.3f} MHz")
        print(f"Generating {duration_seconds}s of synthetic APT signal")
        print("=" * 60)

        n_samples = int(AUDIO_SAMPLE_RATE * duration_seconds)
        t = np.arange(n_samples) / AUDIO_SAMPLE_RATE

        # APT signal: 2400 Hz subcarrier AM-modulated with image data
        subcarrier = np.sin(2 * np.pi * 2400 * t)

        # Simulate line sync pulses (7 pulses of 1040 Hz)
        sync_period = 0.5  # 2 lines per second
        sync_signal = np.zeros(n_samples)
        for i in range(int(duration_seconds / sync_period)):
            start = int(i * sync_period * AUDIO_SAMPLE_RATE)
            end = min(start + int(0.03 * AUDIO_SAMPLE_RATE), n_samples)
            sync_t = np.arange(end - start) / AUDIO_SAMPLE_RATE
            sync_signal[start:end] = np.sin(2 * np.pi * 1040 * sync_t) * 0.8

        # Combine
        signal = 0.5 * subcarrier + 0.3 * sync_signal
        signal += np.random.randn(n_samples) * 0.05  # Add noise

        # Save as raw PCM
        pcm = np.clip(signal * 32767, -32768, 32767).astype(np.int16)

        import wave
        with wave.open(self.output_file, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(AUDIO_SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

        print(f"Synthetic APT saved: {self.output_file} ({n_samples} samples)")
        return True


def main():
    parser = argparse.ArgumentParser(description="NOAA APT Weather Satellite Receiver")
    parser.add_argument("--freq", type=float, default=137.1e6,
                        help="Center frequency in Hz (default: NOAA-19 137.1MHz)")
    parser.add_argument("--output", type=str, default="noaa_apt.wav",
                        help="Output WAV file path")
    parser.add_argument("--duration", type=float, default=600,
                        help="Capture duration in seconds")
    parser.add_argument("--gain", type=float, default=40.0,
                        help="RTL-SDR RF gain in dB")
    parser.add_argument("--simulate", action="store_true",
                        help="Generate synthetic APT signal (no hardware needed)")
    parser.add_argument("--satellite", type=str, default=None,
                        choices=list(NOAA_SATELLITES.keys()),
                        help="Select satellite by name")
    args = parser.parse_args()

    freq = args.freq
    if args.satellite:
        freq = NOAA_SATELLITES[args.satellite]

    receiver = NoaaAptReceiver(
        frequency=freq,
        output_file=args.output,
        gain=args.gain,
    )

    if args.simulate:
        receiver.simulate(args.duration)
    else:
        receiver.run_gnuradio(args.duration)


if __name__ == "__main__":
    main()
