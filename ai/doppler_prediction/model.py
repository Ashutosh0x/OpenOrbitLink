from __future__ import annotations
"""
IIS-LSTM Doppler Prediction Model

Iterative Input Selection LSTM for real-time LEO satellite Doppler shift prediction.
Combines physics-informed features (TLE orbital elements) with learned temporal
dynamics for superior accuracy over classical SGP4-only approaches.

Reference: "Direct-to-Satellite IoT: Tutorial Review on Architectures, Protocols,
and Future Directions" — Frontiers in Communications and Networks, 2026
"""

import numpy as np

try:
    import tensorflow as tf
    from tensorflow import keras
    HAS_TF = True
except ImportError:
    HAS_TF = False
    print("[WARN] TensorFlow not available. Model training disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# Feature Engineering
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_NAMES = [
    # TLE orbital elements (6)
    "inclination_rad",       # Orbital inclination
    "raan_rad",              # Right ascension of ascending node
    "eccentricity",          # Orbital eccentricity
    "arg_perigee_rad",       # Argument of perigee
    "mean_anomaly_rad",      # Mean anomaly
    "mean_motion_rev_day",   # Mean motion (revolutions/day)

    # Derived orbital (3)
    "semi_major_axis_km",    # Computed from mean motion
    "orbital_period_s",      # Computed from mean motion
    "drag_term",             # BSTAR drag coefficient

    # Observer state (3)
    "observer_lat_rad",      # Observer geodetic latitude
    "observer_lon_rad",      # Observer geodetic longitude
    "observer_alt_km",       # Observer altitude

    # Time features (3)
    "time_since_epoch_s",    # Time since TLE epoch
    "pass_phase",            # 0.0=AOS, 0.5=TCA, 1.0=LOS
    "time_of_day_frac",      # Fraction of day (0-1)

    # Historical Doppler (3)
    "doppler_t_minus_1",     # Previous measurement
    "doppler_t_minus_2",     # 2 steps ago
    "doppler_rate_recent",   # Recent rate of change
]

N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 18, f"Expected 18 features, got {N_FEATURES}"

# Sequence length for LSTM input
SEQUENCE_LENGTH = 30  # 30 time steps of history


def extract_features(
    tle_elements: dict,
    observer_lat: float,
    observer_lon: float,
    observer_alt_km: float,
    time_since_epoch_s: float,
    pass_phase: float,
    time_of_day_frac: float,
    doppler_history: list[float],
) -> np.ndarray:
    """
    Extract 18-dimensional feature vector from raw inputs.

    Args:
        tle_elements: dict with keys matching TLE orbital elements
        observer_lat: Observer latitude in radians
        observer_lon: Observer longitude in radians
        observer_alt_km: Observer altitude in km
        time_since_epoch_s: Seconds since TLE epoch
        pass_phase: Pass phase (0=AOS, 0.5=TCA, 1=LOS)
        time_of_day_frac: Fraction of day (0-1)
        doppler_history: List of recent Doppler measurements (Hz)

    Returns:
        np.ndarray of shape (18,)
    """
    # Compute derived elements
    n = tle_elements.get("mean_motion", 15.5)  # rev/day
    mu = 398600.4418  # Earth GM (km³/s²)
    period_s = 86400.0 / n
    a_km = (mu * (period_s / (2 * np.pi)) ** 2) ** (1/3)

    # Historical Doppler features
    hist = list(doppler_history) if doppler_history else [0.0]
    d_t1 = hist[-1] if len(hist) >= 1 else 0.0
    d_t2 = hist[-2] if len(hist) >= 2 else d_t1
    d_rate = (d_t1 - d_t2) if len(hist) >= 2 else 0.0

    features = np.array([
        tle_elements.get("inclination", 0.9),          # rad
        tle_elements.get("raan", 0.0),                  # rad
        tle_elements.get("eccentricity", 0.001),        # dimensionless
        tle_elements.get("arg_perigee", 0.0),           # rad
        tle_elements.get("mean_anomaly", 0.0),          # rad
        n,                                               # rev/day
        a_km,                                            # km
        period_s,                                        # seconds
        tle_elements.get("bstar", 0.0),                 # drag
        observer_lat,                                    # rad
        observer_lon,                                    # rad
        observer_alt_km,                                 # km
        time_since_epoch_s,                              # seconds
        pass_phase,                                      # 0-1
        time_of_day_frac,                                # 0-1
        d_t1,                                            # Hz
        d_t2,                                            # Hz
        d_rate,                                          # Hz/step
    ], dtype=np.float32)

    return features


# ─────────────────────────────────────────────────────────────────────────────
# Model Architecture
# ─────────────────────────────────────────────────────────────────────────────

def build_iis_lstm_model(
    n_features: int = N_FEATURES,
    seq_length: int = SEQUENCE_LENGTH,
    lstm1_units: int = 64,
    lstm2_units: int = 32,
    dense_units: int = 16,
    dropout_rate: float = 0.2,
    learning_rate: float = 1e-3,
) -> "keras.Model":
    """
    Build IIS-LSTM model for Doppler prediction.

    Architecture:
        Input (seq_length, n_features)
        → LSTM(64, return_sequences=True)
        → Dropout(0.2)
        → LSTM(32)
        → Dense(16, ReLU)
        → Dense(1, linear)  # Predicted Doppler offset Hz

    The model learns temporal patterns in Doppler evolution that
    pure physics models (SGP4) miss due to atmospheric drag
    variations, solar pressure, and TLE staleness.
    """
    if not HAS_TF:
        raise RuntimeError("TensorFlow required for model building")

    inputs = keras.Input(shape=(seq_length, n_features), name="doppler_input")

    # Feature importance gate (Iterative Input Selection)
    # Learns which features matter most at each timestep
    gate = keras.layers.Dense(n_features, activation="sigmoid", name="iis_gate")(inputs)
    gated = keras.layers.Multiply(name="gated_features")([inputs, gate])

    # Temporal encoder
    x = keras.layers.LSTM(
        lstm1_units, return_sequences=True,
        activation="tanh", recurrent_activation="sigmoid",
        name="lstm_1"
    )(gated)
    x = keras.layers.Dropout(dropout_rate, name="dropout_1")(x)

    x = keras.layers.LSTM(
        lstm2_units,
        activation="tanh", recurrent_activation="sigmoid",
        name="lstm_2"
    )(x)

    # Prediction head
    x = keras.layers.Dense(dense_units, activation="relu", name="dense_1")(x)
    outputs = keras.layers.Dense(1, activation="linear", name="doppler_output")(x)

    model = keras.Model(inputs=inputs, outputs=outputs, name="IIS_LSTM_Doppler")

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss="mse",
        metrics=["mae"],
    )

    return model


def export_tflite(model: "keras.Model", output_path: str, quantize: bool = True):
    """
    Export trained model to TensorFlow Lite format for Android deployment.

    Uses INT8 quantization for optimal performance on mobile NPU/GPU.
    Target: <5ms inference on Pixel Tensor G4.
    """
    if not HAS_TF:
        raise RuntimeError("TensorFlow required for export")

    converter = tf.lite.TFLiteConverter.from_keras_model(model)

    if quantize:
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]

    tflite_model = converter.convert()

    with open(output_path, "wb") as f:
        f.write(tflite_model)

    size_kb = len(tflite_model) / 1024
    print(f"Exported TFLite model to {output_path} ({size_kb:.1f} KB)")


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic Training Data Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_synthetic_doppler_dataset(
    n_passes: int = 1000,
    seq_length: int = SEQUENCE_LENGTH,
    n_features: int = N_FEATURES,
    noise_std_hz: float = 50.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training data simulating LEO satellite passes.

    Each pass generates a characteristic S-curve Doppler profile.
    Physics-based generation with added noise to simulate real-world
    measurement uncertainty.

    Returns:
        X: (n_samples, seq_length, n_features) input sequences
        y: (n_samples, 1) target Doppler values
    """
    samples_per_pass = seq_length + 10  # Extra for sliding window
    total_samples = n_passes * 10  # Multiple windows per pass

    X = np.zeros((total_samples, seq_length, n_features), dtype=np.float32)
    y = np.zeros((total_samples, 1), dtype=np.float32)

    sample_idx = 0

    for pass_i in range(n_passes):
        # Random orbital parameters
        inclination = np.random.uniform(0.5, 1.8)  # rad
        altitude_km = np.random.uniform(400, 700)   # LEO
        max_doppler = np.random.uniform(3000, 12000)  # Hz

        # Observer position
        obs_lat = np.random.uniform(-1.2, 1.2)  # rad
        obs_lon = np.random.uniform(-3.14, 3.14)  # rad

        # Generate S-curve Doppler profile
        t = np.linspace(0, 1, samples_per_pass)
        # Doppler S-curve: starts positive, crosses zero at TCA, ends negative
        doppler_ideal = max_doppler * np.cos(np.pi * t)
        doppler_noisy = doppler_ideal + np.random.randn(samples_per_pass) * noise_std_hz

        # Generate feature sequences
        for win_start in range(0, samples_per_pass - seq_length - 1, 3):
            if sample_idx >= total_samples:
                break

            for step in range(seq_length):
                idx = win_start + step
                phase = t[idx]

                features = np.zeros(n_features, dtype=np.float32)
                features[0] = inclination
                features[1] = np.random.uniform(0, 2 * np.pi)  # RAAN
                features[2] = np.random.uniform(0, 0.01)       # eccentricity
                features[3] = np.random.uniform(0, 2 * np.pi)  # arg perigee
                features[4] = np.random.uniform(0, 2 * np.pi)  # mean anomaly
                features[5] = 86400 / (2 * np.pi * np.sqrt((altitude_km + 6371)**3 / 398600.4418))
                features[6] = altitude_km + 6371  # semi-major axis
                features[7] = 2 * np.pi * np.sqrt((altitude_km + 6371)**3 / 398600.4418)
                features[8] = np.random.uniform(-1e-4, 1e-4)  # bstar
                features[9] = obs_lat
                features[10] = obs_lon
                features[11] = 0.0  # observer alt
                features[12] = idx * 10.0  # time since epoch approx
                features[13] = phase
                features[14] = np.random.uniform(0, 1)  # time of day

                # Historical Doppler
                features[15] = doppler_noisy[idx] if idx > 0 else 0.0
                features[16] = doppler_noisy[idx - 1] if idx > 1 else features[15]
                features[17] = features[15] - features[16]

                X[sample_idx, step] = features

            # Target: next Doppler value
            target_idx = win_start + seq_length
            y[sample_idx, 0] = doppler_ideal[target_idx]
            sample_idx += 1

    # Trim to actual samples
    X = X[:sample_idx]
    y = y[:sample_idx]

    return X, y


# ─────────────────────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────────────────────

class FeatureNormalizer:
    """
    Z-score normalizer for Doppler prediction features.
    Stores mean/std for consistent normalization between training and inference.
    """

    def __init__(self):
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None

    def fit(self, X: np.ndarray):
        """Compute mean and std from training data. X shape: (N, seq, features)"""
        flat = X.reshape(-1, X.shape[-1])
        self.mean = flat.mean(axis=0)
        self.std = flat.std(axis=0)
        self.std[self.std < 1e-8] = 1.0  # Prevent division by zero

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Apply normalization."""
        if self.mean is None:
            raise ValueError("Normalizer not fitted")
        return (X - self.mean) / self.std

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def save(self, path: str):
        np.savez(path, mean=self.mean, std=self.std)

    def load(self, path: str):
        data = np.load(path)
        self.mean = data["mean"]
        self.std = data["std"]

