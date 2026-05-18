from __future__ import annotations
"""
OpenOrbitLink Link Budget & RF Simulation

Computes end-to-end link budgets for satellite communication paths
and simulates channel conditions (AWGN, Doppler, fading).
"""

import math
import numpy as np
from dataclasses import dataclass


SPEED_OF_LIGHT = 299_792_458.0  # m/s
BOLTZMANN_DB = -228.6           # 10*log10(k) in dBW/K/Hz
EARTH_RADIUS_KM = 6371.0


@dataclass
class LinkBudgetParams:
    """Parameters for satellite link budget calculation."""
    frequency_hz: float = 145.8e6       # VHF amateur
    tx_power_dbm: float = 23.0          # 200mW phone
    tx_antenna_gain_dbi: float = 0.0    # Phone antenna
    tx_cable_loss_db: float = 0.0
    satellite_altitude_km: float = 408.0  # ISS
    elevation_deg: float = 30.0
    sat_antenna_gain_dbi: float = 2.0    # Satellite antenna
    system_noise_temp_k: float = 500.0   # Including sky noise
    bandwidth_hz: float = 1500.0         # Codec2 700bps + FEC
    required_snr_db: float = 6.0         # BPSK with RS+Viterbi
    atmospheric_loss_db: float = 1.0
    polarization_loss_db: float = 0.5
    implementation_loss_db: float = 2.0


def compute_slant_range(altitude_km: float, elevation_deg: float) -> float:
    """Compute slant range from ground to satellite."""
    el_rad = math.radians(elevation_deg)
    Re = EARTH_RADIUS_KM
    h = altitude_km
    return math.sqrt(
        (Re + h)**2 - (Re * math.cos(el_rad))**2
    ) - Re * math.sin(el_rad)


def free_space_path_loss(distance_km: float, frequency_hz: float) -> float:
    """Free Space Path Loss in dB."""
    d_m = distance_km * 1000
    return 20 * math.log10(d_m) + 20 * math.log10(frequency_hz) - 147.55


def compute_link_budget(params: LinkBudgetParams) -> dict:
    """
    Full link budget calculation.
    Returns dict with all intermediate values and final link margin.
    """
    slant_range = compute_slant_range(params.satellite_altitude_km, params.elevation_deg)
    fspl = free_space_path_loss(slant_range, params.frequency_hz)

    # EIRP (Effective Isotropic Radiated Power)
    eirp_dbm = (params.tx_power_dbm +
                params.tx_antenna_gain_dbi -
                params.tx_cable_loss_db)

    # Total path loss
    total_loss_db = (fspl +
                     params.atmospheric_loss_db +
                     params.polarization_loss_db +
                     params.implementation_loss_db)

    # Received power
    rx_power_dbm = eirp_dbm - total_loss_db + params.sat_antenna_gain_dbi

    # Noise floor
    noise_power_dbm = (BOLTZMANN_DB + 30 +  # Convert to dBm
                       10 * math.log10(params.system_noise_temp_k) +
                       10 * math.log10(params.bandwidth_hz))

    # SNR
    snr_db = rx_power_dbm - noise_power_dbm

    # Link margin
    margin_db = snr_db - params.required_snr_db

    return {
        "slant_range_km": slant_range,
        "fspl_db": fspl,
        "eirp_dbm": eirp_dbm,
        "total_loss_db": total_loss_db,
        "rx_power_dbm": rx_power_dbm,
        "noise_power_dbm": noise_power_dbm,
        "snr_db": snr_db,
        "margin_db": margin_db,
        "is_viable": margin_db > 0,
    }


def simulate_awgn_channel(signal: np.ndarray, snr_db: float) -> np.ndarray:
    """Add AWGN noise to signal at specified SNR."""
    signal_power = np.mean(np.abs(signal) ** 2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_power / 2) * (
        np.random.randn(*signal.shape) + 1j * np.random.randn(*signal.shape)
    )
    return signal + noise


def simulate_doppler(
    signal: np.ndarray,
    sample_rate: float,
    doppler_hz: float,
    doppler_rate_hz_s: float = 0.0,
) -> np.ndarray:
    """Apply Doppler frequency shift to signal."""
    t = np.arange(len(signal)) / sample_rate
    freq_offset = doppler_hz + doppler_rate_hz_s * t
    phase = 2 * np.pi * np.cumsum(freq_offset) / sample_rate
    return signal * np.exp(1j * phase)


def print_link_budget(params: LinkBudgetParams):
    """Print formatted link budget report."""
    result = compute_link_budget(params)
    print("=" * 55)
    print("OpenOrbitLink Link Budget Analysis")
    print("=" * 55)
    print(f"  Frequency:         {params.frequency_hz/1e6:.3f} MHz")
    print(f"  Satellite Alt:     {params.satellite_altitude_km:.0f} km")
    print(f"  Elevation:         {params.elevation_deg:.1f}°")
    print(f"  Slant Range:       {result['slant_range_km']:.1f} km")
    print("-" * 55)
    print(f"  TX Power:          {params.tx_power_dbm:.1f} dBm")
    print(f"  TX Antenna Gain:   {params.tx_antenna_gain_dbi:.1f} dBi")
    print(f"  EIRP:              {result['eirp_dbm']:.1f} dBm")
    print(f"  Free Space Loss:   {result['fspl_db']:.1f} dB")
    print(f"  Total Path Loss:   {result['total_loss_db']:.1f} dB")
    print(f"  RX Antenna Gain:   {params.sat_antenna_gain_dbi:.1f} dBi")
    print(f"  RX Power:          {result['rx_power_dbm']:.1f} dBm")
    print(f"  Noise Floor:       {result['noise_power_dbm']:.1f} dBm")
    print("-" * 55)
    print(f"  SNR:               {result['snr_db']:.1f} dB")
    print(f"  Required SNR:      {params.required_snr_db:.1f} dB")
    print(f"  LINK MARGIN:       {result['margin_db']:.1f} dB")
    status = "[OK] VIABLE" if result["is_viable"] else "[X] NOT VIABLE"
    print(f"  Status:            {status}")
    print("=" * 55)


if __name__ == "__main__":
    # ISS link budget at various elevations
    for elev in [10, 20, 30, 45, 60, 90]:
        params = LinkBudgetParams(elevation_deg=elev)
        print_link_budget(params)
        print()

