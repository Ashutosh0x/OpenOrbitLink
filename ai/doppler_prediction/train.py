from __future__ import annotations
"""
OpenOrbitLink Doppler Prediction — Training Pipeline

Trains the IIS-LSTM model on synthetic or real SatNOGS data,
evaluates performance, and exports to TFLite for Android deployment.

Usage:
    python -m ai.doppler_prediction.train --epochs 100 --batch-size 64
    python -m ai.doppler_prediction.train --export-only --model-path models/doppler_best.keras
"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

from .model import (
    build_iis_lstm_model,
    generate_synthetic_doppler_dataset,
    export_tflite,
    FeatureNormalizer,
    SEQUENCE_LENGTH,
    N_FEATURES,
    HAS_TF,
)


def train(
    epochs: int = 100,
    batch_size: int = 64,
    n_train_passes: int = 2000,
    n_val_passes: int = 500,
    learning_rate: float = 1e-3,
    output_dir: str = "models",
    export: bool = True,
):
    """
    Full training pipeline for Doppler prediction model.
    """
    if not HAS_TF:
        print("ERROR: TensorFlow is required for training.")
        print("Install with: pip install tensorflow>=2.16.0")
        sys.exit(1)

    import tensorflow as tf

    os.makedirs(output_dir, exist_ok=True)

    print("=" * 70)
    print("OpenOrbitLink IIS-LSTM Doppler Prediction — Training Pipeline")
    print("=" * 70)

    # ── Generate synthetic training data ──
    print(f"\n[1/5] Generating synthetic training data ({n_train_passes} passes)...")
    t0 = time.perf_counter()
    X_train, y_train = generate_synthetic_doppler_dataset(
        n_passes=n_train_passes, seq_length=SEQUENCE_LENGTH
    )
    print(f"  Train set: X={X_train.shape}, y={y_train.shape} "
          f"[{time.perf_counter()-t0:.1f}s]")

    print(f"\n[2/5] Generating validation data ({n_val_passes} passes)...")
    X_val, y_val = generate_synthetic_doppler_dataset(
        n_passes=n_val_passes, seq_length=SEQUENCE_LENGTH
    )
    print(f"  Val set: X={X_val.shape}, y={y_val.shape}")

    # ── Normalize features ──
    print("\n[3/5] Normalizing features...")
    normalizer = FeatureNormalizer()
    X_train = normalizer.fit_transform(X_train)
    X_val = normalizer.transform(X_val)
    normalizer.save(os.path.join(output_dir, "doppler_normalizer.npz"))
    print(f"  Normalizer saved to {output_dir}/doppler_normalizer.npz")

    # ── Build model ──
    print("\n[4/5] Building IIS-LSTM model...")
    model = build_iis_lstm_model(
        n_features=N_FEATURES,
        seq_length=SEQUENCE_LENGTH,
        learning_rate=learning_rate,
    )
    model.summary()

    # ── Train ──
    print(f"\n[5/5] Training for {epochs} epochs (batch_size={batch_size})...")

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_mae", patience=15, restore_best_weights=True
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_mae", factor=0.5, patience=5, min_lr=1e-6
        ),
        tf.keras.callbacks.ModelCheckpoint(
            os.path.join(output_dir, "doppler_best.keras"),
            monitor="val_mae", save_best_only=True, verbose=1
        ),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        verbose=1,
    )

    # ── Evaluate ──
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    val_loss, val_mae = model.evaluate(X_val, y_val, verbose=0)
    print(f"  Validation MSE:  {val_loss:.2f} Hz²")
    print(f"  Validation MAE:  {val_mae:.2f} Hz")
    print(f"  Validation RMSE: {np.sqrt(val_loss):.2f} Hz")

    # Inference speed test
    dummy_input = np.random.randn(1, SEQUENCE_LENGTH, N_FEATURES).astype(np.float32)
    # Warmup
    for _ in range(10):
        model.predict(dummy_input, verbose=0)

    t0 = time.perf_counter()
    n_infer = 100
    for _ in range(n_infer):
        model.predict(dummy_input, verbose=0)
    avg_ms = (time.perf_counter() - t0) / n_infer * 1000
    print(f"  Avg inference: {avg_ms:.2f} ms/prediction")

    # ── Export TFLite ──
    if export:
        tflite_path = os.path.join(output_dir, "doppler_predictor.tflite")
        print(f"\nExporting TFLite model to {tflite_path}...")
        export_tflite(model, tflite_path, quantize=True)

    print("\n✅ Training pipeline complete!")
    return model, history


def main():
    parser = argparse.ArgumentParser(description="Train OpenOrbitLink Doppler Prediction Model")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--train-passes", type=int, default=2000)
    parser.add_argument("--val-passes", type=int, default=500)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--output-dir", type=str, default="models")
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--model-path", type=str, default=None)
    args = parser.parse_args()

    if args.export_only:
        if not args.model_path:
            print("ERROR: --model-path required with --export-only")
            sys.exit(1)
        if not HAS_TF:
            print("ERROR: TensorFlow required")
            sys.exit(1)
        import tensorflow as tf
        model = tf.keras.models.load_model(args.model_path)
        tflite_path = os.path.join(args.output_dir, "doppler_predictor.tflite")
        export_tflite(model, tflite_path, quantize=True)
    else:
        train(
            epochs=args.epochs,
            batch_size=args.batch_size,
            n_train_passes=args.train_passes,
            n_val_passes=args.val_passes,
            learning_rate=args.lr,
            output_dir=args.output_dir,
            export=not args.no_export,
        )


if __name__ == "__main__":
    main()

