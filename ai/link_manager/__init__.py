from __future__ import annotations
"""
OpenOrbitLink AI Link Manager — Adaptive Multi-Orbital Satellite Selection

Adaptive orbital link selection for consumer devices plus external radio nodes.
Intelligently selects the best satellite link in real-time based on:
- Elevation angle and signal geometry
- Predicted SNR from link budget analysis
- Remaining visibility window duration
- Doppler rate (lower = more stable link)
- Historical success rate per satellite
- Battery state and power budget
- Message priority (SOS > voice > text)

Uses reinforcement learning (Q-learning) to optimize link selection
policy over time based on delivery success feedback.
"""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from enum import IntEnum

import numpy as np


class MessagePriority(IntEnum):
    """Message priority levels for satellite transmission scheduling."""
    SOS = 0        # Emergency — highest priority, immediate transmission
    VOICE = 1      # Voice call — time-sensitive
    TEXT = 2       # Text message — can tolerate delay
    DATA = 3       # Bulk data — lowest priority
    BEACON = 4     # Network beacon — background


@dataclass
class SatelliteCandidate:
    """A visible satellite evaluated for communication."""
    norad_id: int
    name: str
    elevation_deg: float
    azimuth_deg: float
    range_km: float
    doppler_hz: float
    doppler_rate_hz_s: float
    remaining_visibility_s: float
    predicted_snr_db: float
    historical_success_rate: float = 0.5
    supports_uplink: bool = False
    frequency_hz: float = 145_800_000.0

    # Computed by link manager
    score: float = 0.0
    selected: bool = False


@dataclass
class LinkBudget:
    """Satellite link budget calculation results."""
    tx_power_dbm: float           # Transmitter power
    tx_antenna_gain_dbi: float    # Transmitter antenna gain
    path_loss_db: float           # Free-space path loss
    atmospheric_loss_db: float    # Atmospheric attenuation
    rx_antenna_gain_dbi: float    # Receiver antenna gain
    rx_noise_figure_db: float     # Receiver noise figure
    bandwidth_hz: float           # Signal bandwidth
    snr_db: float                 # Resulting SNR
    margin_db: float              # Link margin above threshold

    @property
    def is_viable(self) -> bool:
        """Link is viable if margin > 0."""
        return self.margin_db > 0.0


class OpenOrbitLinkLinkManager:
    """
    Adaptive satellite link selection engine.

    Combines physics-based link budget analysis with learned Q-values
    to select the optimal satellite for each message transmission.
    """

    def __init__(
        self,
        device_tx_power_dbm: float = 20.0,        # External 100 mW LoRa/ISM-class node
        device_antenna_gain_dbi: float = 5.0,     # Small directional external antenna
        min_snr_threshold_db: float = 3.0,         # Minimum usable SNR
        learning_rate: float = 0.1,                # Q-learning alpha
        discount_factor: float = 0.95,             # Q-learning gamma
        exploration_rate: float = 0.1,             # Epsilon-greedy
    ):
        self.device_tx_power_dbm = device_tx_power_dbm
        self.device_antenna_gain_dbi = device_antenna_gain_dbi
        self.min_snr_threshold_db = min_snr_threshold_db
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate

        # Q-table: maps (satellite_id, priority) → expected reward
        self._q_table: dict[tuple[int, int], float] = {}

        # Success tracking
        self._attempts: dict[int, int] = {}
        self._successes: dict[int, int] = {}

    def compute_link_budget(
        self,
        range_km: float,
        frequency_hz: float,
        elevation_deg: float,
        sat_antenna_gain_dbi: float = 2.0,
        bandwidth_hz: float = 1500.0,  # ~700bps BPSK with FEC
    ) -> LinkBudget:
        """
        Compute complete link budget for a satellite path.

        Uses the Friis transmission equation with atmospheric corrections.
        """
        # Free-space path loss (dB)
        # FSPL = 20*log10(d) + 20*log10(f) + 20*log10(4π/c)
        wavelength_m = 299_792_458.0 / frequency_hz
        fspl_db = (20 * math.log10(range_km * 1000) +
                   20 * math.log10(frequency_hz) -
                   147.55)

        # Atmospheric loss varies with elevation
        # Higher elevation = shorter atmospheric path
        if elevation_deg > 10:
            atm_loss_db = 0.5 / math.sin(math.radians(elevation_deg))
        else:
            atm_loss_db = 3.0  # Heavy attenuation at low elevation

        # Noise power
        # N = kTB (k=Boltzmann, T=system noise temp, B=bandwidth)
        noise_temp_k = 290.0 * (10 ** (3.0 / 10) - 1)  # 3dB noise figure
        noise_power_dbm = (-228.6 +  # 10*log10(k) in dBm/K/Hz
                           10 * math.log10(noise_temp_k + 290) +
                           10 * math.log10(bandwidth_hz))

        # Received power
        rx_power_dbm = (self.device_tx_power_dbm +
                        self.device_antenna_gain_dbi -
                        fspl_db -
                        atm_loss_db +
                        sat_antenna_gain_dbi)

        snr_db = rx_power_dbm - noise_power_dbm

        # Required SNR for BPSK with RS+Viterbi FEC: ~3dB for BER < 1e-5
        margin_db = snr_db - self.min_snr_threshold_db

        return LinkBudget(
            tx_power_dbm=self.device_tx_power_dbm,
            tx_antenna_gain_dbi=self.device_antenna_gain_dbi,
            path_loss_db=fspl_db,
            atmospheric_loss_db=atm_loss_db,
            rx_antenna_gain_dbi=sat_antenna_gain_dbi,
            rx_noise_figure_db=3.0,
            bandwidth_hz=bandwidth_hz,
            snr_db=snr_db,
            margin_db=margin_db,
        )

    def score_candidate(
        self,
        candidate: SatelliteCandidate,
        priority: MessagePriority = MessagePriority.TEXT,
    ) -> float:
        """
        Score a satellite candidate using multi-factor weighted evaluation.

        Weights are tuned for different priority levels:
        - SOS: Maximize reliability (elevation + SNR)
        - VOICE: Minimize Doppler + maximize duration
        - TEXT: Balance all factors
        """
        if not candidate.supports_uplink:
            candidate.score = 0.0
            return 0.0

        # Compute link budget
        budget = self.compute_link_budget(
            candidate.range_km,
            candidate.frequency_hz,
            candidate.elevation_deg,
        )
        candidate.predicted_snr_db = budget.snr_db

        if not budget.is_viable:
            return 0.0

        # Normalize factors to [0, 1]
        elev_score = min(candidate.elevation_deg / 90.0, 1.0)
        snr_score = min(max(budget.snr_db / 20.0, 0.0), 1.0)
        duration_score = min(candidate.remaining_visibility_s / 720.0, 1.0)
        doppler_score = 1.0 - min(abs(candidate.doppler_rate_hz_s) / 100.0, 1.0)
        history_score = self._get_success_rate(candidate.norad_id)

        # Priority-dependent weights
        weights = {
            MessagePriority.SOS:    {"elev": 0.35, "snr": 0.35, "dur": 0.15, "dop": 0.05, "hist": 0.10},
            MessagePriority.VOICE:  {"elev": 0.20, "snr": 0.25, "dur": 0.25, "dop": 0.20, "hist": 0.10},
            MessagePriority.TEXT:   {"elev": 0.25, "snr": 0.25, "dur": 0.20, "dop": 0.15, "hist": 0.15},
            MessagePriority.DATA:   {"elev": 0.20, "snr": 0.20, "dur": 0.30, "dop": 0.10, "hist": 0.20},
            MessagePriority.BEACON: {"elev": 0.30, "snr": 0.30, "dur": 0.10, "dop": 0.10, "hist": 0.20},
        }
        w = weights.get(priority, weights[MessagePriority.TEXT])

        # Q-value bonus from reinforcement learning
        q_key = (candidate.norad_id, int(priority))
        q_bonus = self._q_table.get(q_key, 0.0)

        score = (
            w["elev"] * elev_score +
            w["snr"] * snr_score +
            w["dur"] * duration_score +
            w["dop"] * doppler_score +
            w["hist"] * history_score +
            0.1 * np.tanh(q_bonus)  # Bounded Q contribution
        )

        candidate.score = score
        return score

    def select_best(
        self,
        candidates: list[SatelliteCandidate],
        priority: MessagePriority = MessagePriority.TEXT,
    ) -> Optional[SatelliteCandidate]:
        """
        Select the best satellite from candidates.

        Uses epsilon-greedy exploration to occasionally try
        non-optimal satellites for learning.
        """
        if not candidates:
            return None

        # Score all candidates
        for c in candidates:
            self.score_candidate(c, priority)

        # Filter viable candidates
        viable = [c for c in candidates if c.score > 0.0]
        if not viable:
            return None

        # Epsilon-greedy selection
        if np.random.random() < self.epsilon:
            # Explore: random selection
            selected = viable[np.random.randint(len(viable))]
        else:
            # Exploit: best score
            selected = max(viable, key=lambda c: c.score)

        selected.selected = True
        return selected

    def report_outcome(
        self,
        norad_id: int,
        priority: MessagePriority,
        success: bool,
        delivery_time_s: float = 0.0,
    ):
        """
        Report transmission outcome for Q-learning update.

        Called after each transmission attempt to update the
        learned policy.
        """
        # Update success tracking
        self._attempts[norad_id] = self._attempts.get(norad_id, 0) + 1
        if success:
            self._successes[norad_id] = self._successes.get(norad_id, 0) + 1

        # Q-learning update
        q_key = (norad_id, int(priority))
        old_q = self._q_table.get(q_key, 0.0)

        # Reward: +1 for success, -0.5 for failure, bonus for fast delivery
        reward = 1.0 if success else -0.5
        if success and delivery_time_s > 0:
            speed_bonus = max(0, 1.0 - delivery_time_s / 300.0)  # Bonus for <5min
            reward += 0.5 * speed_bonus

        # Q-update: Q(s,a) ← Q(s,a) + α[r + γ·max_a'Q(s',a') - Q(s,a)]
        # Simplified: no next-state, just direct update
        new_q = old_q + self.lr * (reward - old_q)
        self._q_table[q_key] = new_q

    def _get_success_rate(self, norad_id: int) -> float:
        """Get historical success rate for a satellite."""
        attempts = self._attempts.get(norad_id, 0)
        if attempts == 0:
            return 0.5  # Prior: 50% for unknown satellites
        successes = self._successes.get(norad_id, 0)
        return successes / attempts

    def get_status(self) -> dict:
        """Get link manager status for diagnostics."""
        return {
            "total_satellites_tracked": len(self._attempts),
            "q_table_size": len(self._q_table),
            "exploration_rate": self.epsilon,
            "satellite_stats": {
                nid: {
                    "attempts": self._attempts[nid],
                    "successes": self._successes.get(nid, 0),
                    "success_rate": self._get_success_rate(nid),
                }
                for nid in self._attempts
            },
        }
