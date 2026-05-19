from __future__ import annotations

"""
OpenOrbitLink DSP — Codec2 Python Wrapper & SDR Signal Processing Utilities

Provides high-level Python interface to Codec2 voice codec and
signal processing utilities for satellite signal decoding.
"""

import struct
import numpy as np
from typing import Optional, List

from protocol.aprs import (
    AX25Address,
    build_ax25_ui_frame as _build_ax25_ui_frame,
    encode_ax25_address as _encode_ax25_address,
    parse_callsign,
)


# ─── Audio Utilities ────────────────────────────────────────────────────────

SAMPLE_RATE = 8000
FRAME_MS = 40
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 320


def generate_tone(freq_hz: float, duration_ms: float, amplitude: float = 0.8) -> np.ndarray:
    """Generate a pure sine tone at the given frequency."""
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(n_samples) / SAMPLE_RATE
    return (np.sin(2 * np.pi * freq_hz * t) * amplitude * 32767).astype(np.int16)


def pcm_to_float(pcm: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 [-1, 1]."""
    return pcm.astype(np.float32) / 32768.0


def float_to_pcm(audio: np.ndarray) -> np.ndarray:
    """Convert float32 [-1, 1] to int16 PCM."""
    return np.clip(audio * 32768, -32768, 32767).astype(np.int16)


def compute_rms(pcm: np.ndarray) -> float:
    """Compute RMS energy of PCM samples."""
    return float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))


def compute_snr(signal: np.ndarray, noise: np.ndarray) -> float:
    """Compute SNR in dB between signal and noise arrays."""
    sig_power = np.mean(signal.astype(np.float64) ** 2)
    noise_power = np.mean(noise.astype(np.float64) ** 2)
    if noise_power < 1e-10:
        return 100.0
    return 10 * np.log10(sig_power / noise_power)


# ─── BPSK Modulation / Demodulation ────────────────────────────────────────

def bpsk_modulate(bits: np.ndarray, samples_per_symbol: int = 8) -> np.ndarray:
    """
    BPSK modulate a bit array.
    Maps 0 → -1.0, 1 → +1.0, then upsamples.
    """
    symbols = 2.0 * bits.astype(np.float64) - 1.0
    # Upsample
    signal = np.repeat(symbols, samples_per_symbol)
    return signal


def bpsk_demodulate(signal: np.ndarray, samples_per_symbol: int = 8) -> np.ndarray:
    """
    BPSK demodulate a baseband signal.
    Integrates over symbol period and slices.
    """
    n_symbols = len(signal) // samples_per_symbol
    bits = np.zeros(n_symbols, dtype=np.int32)
    for i in range(n_symbols):
        chunk = signal[i * samples_per_symbol:(i + 1) * samples_per_symbol]
        bits[i] = 1 if np.sum(chunk) > 0 else 0
    return bits


# ─── Barker Code Synchronization ───────────────────────────────────────────

BARKER_13 = np.array([1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1], dtype=np.float64)


def barker_correlate(signal: np.ndarray, threshold: float = 10.0) -> List[int]:
    """
    Find Barker-13 sync positions in a BPSK signal.
    Returns list of sample indices where sync is detected.
    """
    corr = np.correlate(signal, BARKER_13, mode='valid')
    peak = np.max(np.abs(corr))
    if peak < threshold:
        return []
    positions = np.where(np.abs(corr) > threshold)[0]
    return positions.tolist()


# ─── Doppler Shift Utilities ───────────────────────────────────────────────

def apply_doppler(signal: np.ndarray, sample_rate: float,
                  doppler_hz: float) -> np.ndarray:
    """Apply constant Doppler frequency shift to a complex signal."""
    t = np.arange(len(signal)) / sample_rate
    shift = np.exp(2j * np.pi * doppler_hz * t)
    if np.isrealobj(signal):
        return np.real(signal.astype(np.complex128) * shift)
    return signal * shift


def remove_doppler(signal: np.ndarray, sample_rate: float,
                   doppler_hz: float) -> np.ndarray:
    """Remove known Doppler shift from signal."""
    return apply_doppler(signal, sample_rate, -doppler_hz)


# ─── Reed-Solomon Helper ──────────────────────────────────────────────────

def compute_parity(data: bytes, n_parity: int = 32) -> bytes:
    """Compute simple XOR-based parity bytes (development stand-in for RS)."""
    parity = bytearray(n_parity)
    for i, b in enumerate(data):
        parity[i % n_parity] ^= b
    return bytes(parity)


def verify_parity(data: bytes, parity: bytes) -> int:
    """Verify parity and return number of detected errors."""
    expected = compute_parity(data, len(parity))
    return sum(1 for a, b in zip(parity, expected) if a != b)


# ─── AX.25 Frame Helpers ─────────────────────────────────────────────────

def encode_ax25_address(callsign: str, ssid: int = 0, last: bool = False) -> bytes:
    """Encode a callsign into AX.25 address field (7 bytes)."""
    return _encode_ax25_address(AX25Address(callsign.upper(), ssid), last=last)


def build_ax25_ui_frame(source: str, dest: str, payload: bytes) -> bytes:
    """
    Build a simple AX.25 UI (Unnumbered Information) frame.
    Used for ISS APRS digipeater communication.
    """
    parse_callsign(source)
    parse_callsign(dest)
    return _build_ax25_ui_frame(source, dest, payload)
