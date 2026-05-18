from __future__ import annotations

"""
OpenOrbitLink Link Budget & RF Simulation.

The defaults model a real transmit path: an external LoRa ISM node with a
small directional antenna. Android phones and RTL-SDR dongles are not modeled
as direct arbitrary RF transmitters.
"""

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


SPEED_OF_LIGHT = 299_792_458.0  # m/s
BOLTZMANN_DB = -228.6           # 10*log10(k) in dBW/K/Hz
EARTH_RADIUS_KM = 6371.0


class TxPath(str, Enum):
    LORA_ISM_UPLINK = "lora_ism_uplink"
    HAM_SDR_UPLINK = "ham_sdr_uplink"
    HACKRF_EXPERIMENTAL = "hackrf_experimental"
    CARRIER_NTN = "carrier_ntn"
    ANDROID_NTN = "android_ntn"
    RTL_SDR_RX_ONLY = "rtl_sdr_rx_only"


@dataclass(frozen=True)
class TxPathProfile:
    tx_capable: bool
    frequency_hz: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    tx_cable_loss_db: float
    bandwidth_hz: float
    required_snr_db: float
    note: str


TX_PATH_PROFILES: dict[TxPath, TxPathProfile] = {
    TxPath.LORA_ISM_UPLINK: TxPathProfile(
        tx_capable=True,
        frequency_hz=868.1e6,
        tx_power_dbm=20.0,          # 100 mW class external LoRa node
        tx_antenna_gain_dbi=5.0,
        tx_cable_loss_db=1.0,
        bandwidth_hz=125_000.0,
        required_snr_db=-12.0,
        note="External LoRa ISM node; region-specific frequency and duty-cycle limits still apply.",
    ),
    TxPath.HAM_SDR_UPLINK: TxPathProfile(
        tx_capable=True,
        frequency_hz=145.825e6,
        tx_power_dbm=30.0,          # 1 W amateur station, not a phone
        tx_antenna_gain_dbi=7.0,
        tx_cable_loss_db=1.5,
        bandwidth_hz=1_200.0,
        required_snr_db=6.0,
        note="Licensed amateur station only; no encryption or commercial traffic.",
    ),
    TxPath.HACKRF_EXPERIMENTAL: TxPathProfile(
        tx_capable=True,
        frequency_hz=435.0e6,
        tx_power_dbm=14.0,
        tx_antenna_gain_dbi=5.0,
        tx_cable_loss_db=1.5,
        bandwidth_hz=2_400.0,
        required_snr_db=7.0,
        note="Lab/experimental SDR path requiring filtering, amplification, and legal authorization.",
    ),
    TxPath.CARRIER_NTN: TxPathProfile(
        tx_capable=False,
        frequency_hz=2.0e9,
        tx_power_dbm=0.0,
        tx_antenna_gain_dbi=0.0,
        tx_cable_loss_db=0.0,
        bandwidth_hz=180_000.0,
        required_snr_db=0.0,
        note="Carrier-managed; latency ~600 ms LEO, throughput SMS-class; no open uplink.",
    ),
    TxPath.ANDROID_NTN: TxPathProfile(
        tx_capable=False,
        frequency_hz=2.0e9,
        tx_power_dbm=0.0,
        tx_antenna_gain_dbi=0.0,
        tx_cable_loss_db=0.0,
        bandwidth_hz=180_000.0,
        required_snr_db=0.0,
        note="Carrier-managed 3GPP NTN only; apps cannot arbitrarily transmit satellite RF.",
    ),
    TxPath.RTL_SDR_RX_ONLY: TxPathProfile(
        tx_capable=False,
        frequency_hz=145.825e6,
        tx_power_dbm=float("-inf"),
        tx_antenna_gain_dbi=0.0,
        tx_cable_loss_db=0.0,
        bandwidth_hz=1_200.0,
        required_snr_db=6.0,
        note="RTL-SDR hardware is receive-only and cannot be an uplink path.",
    ),
}


@dataclass
class LinkBudgetParams:
    """Parameters for satellite link budget calculation."""

    tx_path: TxPath = TxPath.LORA_ISM_UPLINK
    frequency_hz: float | None = None
    tx_power_dbm: float | None = None
    tx_antenna_gain_dbi: float | None = None
    tx_cable_loss_db: float | None = None
    satellite_altitude_km: float = 550.0
    elevation_deg: float = 30.0
    sat_antenna_gain_dbi: float = 2.0
    system_noise_temp_k: float = 500.0
    bandwidth_hz: float | None = None
    required_snr_db: float | None = None
    atmospheric_loss_db: float = 1.0
    polarization_loss_db: float = 1.0
    implementation_loss_db: float = 2.0

    def resolved(self) -> "ResolvedLinkBudgetParams":
        profile = TX_PATH_PROFILES[self.tx_path]
        return ResolvedLinkBudgetParams(
            tx_path=self.tx_path,
            tx_capable=profile.tx_capable,
            tx_path_note=profile.note,
            frequency_hz=profile.frequency_hz if self.frequency_hz is None else self.frequency_hz,
            tx_power_dbm=profile.tx_power_dbm if self.tx_power_dbm is None else self.tx_power_dbm,
            tx_antenna_gain_dbi=(
                profile.tx_antenna_gain_dbi if self.tx_antenna_gain_dbi is None else self.tx_antenna_gain_dbi
            ),
            tx_cable_loss_db=profile.tx_cable_loss_db if self.tx_cable_loss_db is None else self.tx_cable_loss_db,
            satellite_altitude_km=self.satellite_altitude_km,
            elevation_deg=self.elevation_deg,
            sat_antenna_gain_dbi=self.sat_antenna_gain_dbi,
            system_noise_temp_k=self.system_noise_temp_k,
            bandwidth_hz=profile.bandwidth_hz if self.bandwidth_hz is None else self.bandwidth_hz,
            required_snr_db=profile.required_snr_db if self.required_snr_db is None else self.required_snr_db,
            atmospheric_loss_db=self.atmospheric_loss_db,
            polarization_loss_db=self.polarization_loss_db,
            implementation_loss_db=self.implementation_loss_db,
        )


@dataclass(frozen=True)
class ResolvedLinkBudgetParams:
    tx_path: TxPath
    tx_capable: bool
    tx_path_note: str
    frequency_hz: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    tx_cable_loss_db: float
    satellite_altitude_km: float
    elevation_deg: float
    sat_antenna_gain_dbi: float
    system_noise_temp_k: float
    bandwidth_hz: float
    required_snr_db: float
    atmospheric_loss_db: float
    polarization_loss_db: float
    implementation_loss_db: float


@dataclass(frozen=True)
class ThroughputAnalysis:
    payload_bytes: int
    raw_bitrate_bps: float
    header_bytes: int
    fec_parity_bytes: int
    crc_bytes: int
    total_tx_bytes: int
    tx_time_seconds: float
    effective_payload_bps: float
    overhead_percent: float
    note: str


def params_for_path(tx_path: TxPath, **overrides) -> LinkBudgetParams:
    return LinkBudgetParams(tx_path=tx_path, **overrides)


def compute_slant_range(altitude_km: float, elevation_deg: float) -> float:
    """Compute slant range from ground to satellite."""
    el_rad = math.radians(elevation_deg)
    re = EARTH_RADIUS_KM
    h = altitude_km
    return math.sqrt((re + h) ** 2 - (re * math.cos(el_rad)) ** 2) - re * math.sin(el_rad)


def free_space_path_loss(distance_km: float, frequency_hz: float) -> float:
    """Free Space Path Loss in dB."""
    d_m = distance_km * 1000
    return 20 * math.log10(d_m) + 20 * math.log10(frequency_hz) - 147.55


def analyze_throughput(
    payload_bytes: int,
    raw_bitrate_bps: float = 700.0,
    header_bytes: int = 21,
    fec_parity_bytes: int = 32,
    crc_bytes: int = 2,
) -> ThroughputAnalysis:
    """Estimate effective payload throughput for one OpenOrbitLink packet."""
    if payload_bytes < 0:
        raise ValueError("payload_bytes must be non-negative")
    if raw_bitrate_bps <= 0:
        raise ValueError("raw_bitrate_bps must be positive")
    total_tx_bytes = payload_bytes + header_bytes + fec_parity_bytes + crc_bytes
    tx_time_seconds = (total_tx_bytes * 8) / raw_bitrate_bps
    effective_payload_bps = 0.0 if tx_time_seconds == 0 else (payload_bytes * 8) / tx_time_seconds
    overhead_bytes = total_tx_bytes - payload_bytes
    overhead_percent = 0.0 if total_tx_bytes == 0 else 100.0 * overhead_bytes / total_tx_bytes
    return ThroughputAnalysis(
        payload_bytes=payload_bytes,
        raw_bitrate_bps=raw_bitrate_bps,
        header_bytes=header_bytes,
        fec_parity_bytes=fec_parity_bytes,
        crc_bytes=crc_bytes,
        total_tx_bytes=total_tx_bytes,
        tx_time_seconds=tx_time_seconds,
        effective_payload_bps=effective_payload_bps,
        overhead_percent=overhead_percent,
        note="RS/FEC accounting here models the current fixed 32-byte parity field; RS(255,223) block interleaving would add more overhead for larger ADUs.",
    )


def compute_link_budget(params: LinkBudgetParams) -> dict:
    """Full link budget calculation with honest TX-path viability."""
    resolved = params.resolved()
    slant_range = compute_slant_range(resolved.satellite_altitude_km, resolved.elevation_deg)
    fspl = free_space_path_loss(slant_range, resolved.frequency_hz)

    if not resolved.tx_capable:
        return {
            "tx_path": resolved.tx_path.value,
            "tx_capable": False,
            "reason": resolved.tx_path_note,
            "slant_range_km": slant_range,
            "fspl_db": fspl,
            "eirp_dbm": float("-inf"),
            "total_loss_db": float("inf"),
            "rx_power_dbm": float("-inf"),
            "noise_power_dbm": None,
            "snr_db": float("-inf"),
            "margin_db": float("-inf"),
            "is_viable": False,
        }

    eirp_dbm = resolved.tx_power_dbm + resolved.tx_antenna_gain_dbi - resolved.tx_cable_loss_db
    total_loss_db = (
        fspl
        + resolved.atmospheric_loss_db
        + resolved.polarization_loss_db
        + resolved.implementation_loss_db
    )
    rx_power_dbm = eirp_dbm - total_loss_db + resolved.sat_antenna_gain_dbi
    noise_power_dbm = (
        BOLTZMANN_DB
        + 30
        + 10 * math.log10(resolved.system_noise_temp_k)
        + 10 * math.log10(resolved.bandwidth_hz)
    )
    snr_db = rx_power_dbm - noise_power_dbm
    margin_db = snr_db - resolved.required_snr_db

    return {
        "tx_path": resolved.tx_path.value,
        "tx_capable": True,
        "reason": resolved.tx_path_note,
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
    resolved = params.resolved()
    result = compute_link_budget(params)
    print("=" * 55)
    print("OpenOrbitLink Link Budget Analysis")
    print("=" * 55)
    print(f"  TX Path:           {resolved.tx_path.value}")
    print(f"  Frequency:         {resolved.frequency_hz/1e6:.3f} MHz")
    print(f"  Satellite Alt:     {resolved.satellite_altitude_km:.0f} km")
    print(f"  Elevation:         {resolved.elevation_deg:.1f} deg")
    print(f"  Slant Range:       {result['slant_range_km']:.1f} km")
    print("-" * 55)
    print(f"  TX Capable:        {result['tx_capable']}")
    print(f"  Note:              {result['reason']}")
    if result["tx_capable"]:
        print(f"  TX Power:          {resolved.tx_power_dbm:.1f} dBm")
        print(f"  TX Antenna Gain:   {resolved.tx_antenna_gain_dbi:.1f} dBi")
        print(f"  EIRP:              {result['eirp_dbm']:.1f} dBm")
        print(f"  Free Space Loss:   {result['fspl_db']:.1f} dB")
        print(f"  Total Path Loss:   {result['total_loss_db']:.1f} dB")
        print(f"  RX Antenna Gain:   {resolved.sat_antenna_gain_dbi:.1f} dBi")
        print(f"  RX Power:          {result['rx_power_dbm']:.1f} dBm")
        print(f"  Noise Floor:       {result['noise_power_dbm']:.1f} dBm")
        print("-" * 55)
        print(f"  SNR:               {result['snr_db']:.1f} dB")
        print(f"  Required SNR:      {resolved.required_snr_db:.1f} dB")
        print(f"  LINK MARGIN:       {result['margin_db']:.1f} dB")
    status = "[OK] VIABLE" if result["is_viable"] else "[X] NOT VIABLE"
    print(f"  Status:            {status}")
    print("=" * 55)


if __name__ == "__main__":
    for path in [TxPath.RTL_SDR_RX_ONLY, TxPath.LORA_ISM_UPLINK, TxPath.HAM_SDR_UPLINK, TxPath.CARRIER_NTN]:
        for elev in [10, 30, 60, 90]:
            print_link_budget(LinkBudgetParams(tx_path=path, elevation_deg=elev))
            print()
