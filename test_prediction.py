"""Quick script to test the deployed AI model on a specific participant window."""
import argparse
import pickle
import random
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

ROOT = Path(__file__).parent
MODEL_PATH = ROOT / "models" / "heart_anomaly_model.pkl"
SCALER_PATH = ROOT / "models" / "scaler.pkl"
DATA_PATH = ROOT / "ai_model_training" / "data" / "processed" / "cleaned_sensor_data.csv"
WINDOW_SIZE = 64
FEATURE_COLS = ["accel_x", "temperature", "pulse_rate", "spo2"]


def load_model_and_scaler():
    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)
    model = tf.keras.models.model_from_json(artifact["model_config"])
    model.set_weights(artifact["weights"])

    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    return model, scaler


def pick_sequence(df: pd.DataFrame, participant: str | None, start: int | None, seed: int) -> pd.DataFrame:
    if participant:
        subset = df[df["participant_id"] == participant].reset_index(drop=True)
        if subset.empty:
            raise ValueError(f"Khong tim thay participant_id='{participant}' trong file {DATA_PATH}")
    else:
        subset = df.reset_index(drop=True)

    if len(subset) < WINDOW_SIZE:
        raise ValueError(
            f"Du lieu cua participant '{participant or 'ALL'}' chi co {len(subset)} dong, khong du {WINDOW_SIZE} dong."
        )

    max_start = len(subset) - WINDOW_SIZE
    if max_start < 0:
        raise ValueError("Khong co du lieu de tao cua so 64 dong")

    if start is None:
        random.seed(seed)
        start = random.randint(0, max_start)
    elif start < 0 or start > max_start:
        raise ValueError(f"start={start} khong hop le (0 <= start <= {max_start})")

    return subset.iloc[start : start + WINDOW_SIZE]


def main():
    parser = argparse.ArgumentParser(description="Test nhanh AI model theo participant")
    parser.add_argument("--participant", "-p", help="participant_id (vd: D1, N2, ...)")
    parser.add_argument("--start", type=int, help="index bat dau (0-based) trong participant, mac dinh random")
    parser.add_argument("--seed", type=int, default=42, help="seed dung cho random khi khong chi dinh start")
    args = parser.parse_args()

    df = pd.read_csv(DATA_PATH)
    missing = [c for c in FEATURE_COLS + ["participant_id", "label"] if c not in df.columns]
    if missing:
        raise ValueError(f"File {DATA_PATH} thieu cac cot: {missing}")

    model, scaler = load_model_and_scaler()
    window_df = pick_sequence(df, args.participant, args.start, args.seed)

    X = window_df[FEATURE_COLS].to_numpy()
    X_scaled = scaler.transform(X).reshape(1, WINDOW_SIZE, len(FEATURE_COLS))

    prob = float(model.predict(X_scaled, verbose=0)[0][0])
    pred = 1 if prob >= 0.5 else 0
    true_label = int(window_df["label"].iloc[-1])

    print("=== THONG TIN CUA SO TEST ===")
    print(f"Participant: {window_df['participant_id'].iloc[0]}")
    print(f"Dong bat dau: {window_df.index[0]} (trong subset da chon)")
    print(f"Nhan thuc te (label): {true_label}")
    print("--- Ket qua mo hinh ---")
    print(f"Xac suat MDD: {prob:.4f} -> Ket luan: {'Bat thuong' if pred else 'Binh thuong'}")


if __name__ == "__main__":
    main()
