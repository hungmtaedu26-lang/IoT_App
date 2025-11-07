import os
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "TensorFlow chưa được cài đặt. Vui lòng thêm 'tensorflow' vào requirements "
        "và cài đặt trước khi chạy model_selected.py."
    ) from exc

from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.utils import class_weight


RANDOM_STATE = 42
np.random.seed(RANDOM_STATE)
tf.random.set_seed(RANDOM_STATE)


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "processed" / "cleaned_sensor_data.csv"
OUTPUT_DIR = BASE_DIR / "evaluation_results" / "model_selected"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = BASE_DIR.parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_ARTIFACT_PATH = MODEL_DIR / "heart_anomaly_model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"

sensor_cols = ["accel_x", "temperature", "pulse_rate", "spo2"]


def load_clean_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dữ liệu '{DATA_PATH}'. "
            "Hãy chạy script 1_preprocess.py để tạo cleaned_sensor_data.csv."
        )
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=sensor_cols + ["label", "participant_id"])
    df[sensor_cols] = df[sensor_cols].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=sensor_cols)
    df["label"] = df["label"].astype(int)
    return df


def create_sequences_from_array(
    arr: np.ndarray, window: int, step: int
) -> List[np.ndarray]:
    if len(arr) == 0:
        return []
    if len(arr) < window:
        pad_len = window - len(arr)
        padded = np.pad(arr, ((0, pad_len), (0, 0)), mode="edge")
        return [padded.astype(np.float32)]

    sequences = []
    for start in range(0, len(arr) - window + 1, step):
        sequences.append(arr[start : start + window].astype(np.float32))
    if (len(arr) - window) % step != 0:
        sequences.append(arr[-window:].astype(np.float32))
    return sequences


def build_sequence_dataset(
    participant_ids: List[str],
    scaled_data: Dict[str, np.ndarray],
    labels: Dict[str, int],
    window: int,
    step: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    seqs: List[np.ndarray] = []
    seq_labels: List[int] = []
    seq_groups: List[str] = []
    for pid in participant_ids:
        series = scaled_data[pid]
        windows = create_sequences_from_array(series, window=window, step=step)
        if not windows:
            continue
        seqs.extend(windows)
        seq_labels.extend([labels[pid]] * len(windows))
        seq_groups.extend([pid] * len(windows))
    if not seqs:
        return np.empty((0, window, len(sensor_cols)), dtype=np.float32), np.empty(
            (0,), dtype=np.int32
        ), np.empty((0,), dtype=object)
    X = np.stack(seqs).astype(np.float32)
    y = np.array(seq_labels, dtype=np.int32)
    groups = np.array(seq_groups, dtype=object)
    return X, y, groups


def build_model(input_shape: Tuple[int, int]) -> keras.Model:
    model = keras.Sequential(
        [
            layers.Input(shape=input_shape),
            layers.Conv1D(64, kernel_size=3, padding="same"),
            layers.BatchNormalization(),
            layers.Activation("relu"),
            layers.Conv1D(64, kernel_size=3, padding="same"),
            layers.BatchNormalization(),
            layers.Activation("relu"),
            layers.MaxPooling1D(pool_size=2),
            layers.Dropout(0.3),
            layers.Conv1D(128, kernel_size=3, padding="same"),
            layers.BatchNormalization(),
            layers.Activation("relu"),
            layers.MaxPooling1D(pool_size=2),
            layers.Dropout(0.3),
            layers.LSTM(64, return_sequences=False),
            layers.Dropout(0.3),
            layers.Dense(32, activation="relu"),
            layers.Dropout(0.2),
            layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model


def safe_log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    probs = np.clip(probs, 1e-10, 1 - 1e-10)
    stacked = np.column_stack([1 - probs, probs])
    return log_loss(y_true, stacked, labels=[0, 1])


def evaluate_logo_folds(
    df: pd.DataFrame,
    data_by_pid: Dict[str, np.ndarray],
    label_by_pid: Dict[str, int],
    window_size: int,
    step_size: int,
    max_epochs: int,
) -> Tuple[List[Dict[str, float]], Dict]:
    logo = LeaveOneGroupOut()
    groups = df["participant_id"]

    fold_metrics: List[Dict[str, float]] = []
    best_fold: Dict = {"metric": -np.inf}

    for fold_idx, (train_idx, test_idx) in enumerate(
        logo.split(df[sensor_cols], df["label"], groups=groups), start=1
    ):
        train_pids = sorted(groups.iloc[train_idx].unique())
        test_pids = sorted(groups.iloc[test_idx].unique())

        scaler = StandardScaler()
        stacked_train = np.vstack([data_by_pid[pid] for pid in train_pids])
        scaler.fit(stacked_train)

        scaled_data = {
            pid: scaler.transform(data_by_pid[pid]) for pid in train_pids + test_pids
        }

        X_train_seq, y_train_seq, _ = build_sequence_dataset(
            train_pids, scaled_data, label_by_pid, window_size, step_size
        )
        X_test_seq, y_test_seq, test_seq_pid = build_sequence_dataset(
            test_pids, scaled_data, label_by_pid, window_size, step_size
        )

        if len(X_train_seq) == 0 or len(X_test_seq) == 0:
            print(f"[Fold {fold_idx}] Không đủ dữ liệu sau khi tạo chuỗi. Bỏ qua.")
            continue

        stratify = y_train_seq if len(np.unique(y_train_seq)) > 1 else None
        try:
            X_tr, X_val, y_tr, y_val = train_test_split(
                X_train_seq,
                y_train_seq,
                test_size=0.2,
                random_state=RANDOM_STATE,
                stratify=stratify,
            )
        except ValueError:
            X_tr, X_val, y_tr, y_val = train_test_split(
                X_train_seq,
                y_train_seq,
                test_size=0.2,
                random_state=RANDOM_STATE,
                stratify=None,
            )

        classes = np.unique(y_tr)
        class_weights = {
            int(cls): weight
            for cls, weight in zip(
                classes,
                class_weight.compute_class_weight(
                    class_weight="balanced", classes=classes, y=y_tr
                ),
            )
        }

        model = build_model(input_shape=(window_size, len(sensor_cols)))
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=12, restore_best_weights=True
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=6, min_lr=1e-5
            ),
        ]

        history = model.fit(
            X_tr,
            y_tr,
            epochs=max_epochs,
            batch_size=32,
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            class_weight=class_weights if len(classes) > 1 else None,
            verbose=0,
        )

        best_epoch = int(np.argmin(history.history["val_loss"]))
        val_acc = float(history.history["val_accuracy"][best_epoch])

        test_probs_seq = model.predict(X_test_seq, verbose=0).squeeze()
        if test_probs_seq.ndim == 0:
            test_probs_seq = np.array([float(test_probs_seq)])

        prob_by_pid: Dict[str, List[float]] = {}
        for prob, pid in zip(test_probs_seq, test_seq_pid):
            prob_by_pid.setdefault(pid, []).append(float(prob))

        fold_results = []
        for pid, probs in prob_by_pid.items():
            avg_prob = float(np.mean(probs))
            fold_results.append((pid, avg_prob))

        y_true_fold = np.array([label_by_pid[pid] for pid, _ in fold_results])
        y_prob_fold = np.array([prob for _, prob in fold_results])
        y_pred_fold = (y_prob_fold >= 0.5).astype(int)

        metrics = {
            "Fold": fold_idx,
            "Participants": len(fold_results),
            "Accuracy": accuracy_score(y_true_fold, y_pred_fold),
            "F1": f1_score(y_true_fold, y_pred_fold, zero_division=0),
            "ROC AUC": roc_auc_score(y_true_fold, y_prob_fold),
            "Brier Score": brier_score_loss(y_true_fold, y_prob_fold),
            "Log Loss": safe_log_loss(y_true_fold, y_prob_fold),
            "Val Accuracy": val_acc,
        }
        fold_metrics.append(metrics)

        if metrics["F1"] > best_fold["metric"]:
            best_fold = {
                "metric": metrics["F1"],
                "fold_idx": fold_idx,
                "scaler_state": {
                    "mean": scaler.mean_.copy(),
                    "scale": scaler.scale_.copy(),
                    "var": scaler.var_.copy(),
                },
                "train_pids": train_pids,
                "test_pids": test_pids,
            }

    if not fold_metrics:
        raise RuntimeError("Không có fold nào được đánh giá thành công.")

    return fold_metrics, best_fold


def train_full_model(
    participants: List[str],
    data_by_pid: Dict[str, np.ndarray],
    label_by_pid: Dict[str, int],
    window_size: int,
    step_size: int,
    max_epochs: int,
) -> Tuple[keras.Model, StandardScaler]:
    scaler = StandardScaler()
    stacked = np.vstack([data_by_pid[pid] for pid in participants])
    scaler.fit(stacked)
    scaled_data = {pid: scaler.transform(data_by_pid[pid]) for pid in participants}

    X_full, y_full, _ = build_sequence_dataset(
        participants, scaled_data, label_by_pid, window_size, step_size
    )
    if len(X_full) == 0:
        raise RuntimeError("Không tạo được chuỗi nào cho toàn bộ dữ liệu.")

    classes = np.unique(y_full)
    class_weights = {
        int(cls): weight
        for cls, weight in zip(
            classes,
            class_weight.compute_class_weight(
                class_weight="balanced", classes=classes, y=y_full
            ),
        )
    }

    model = build_model(input_shape=(window_size, len(sensor_cols)))
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="loss", patience=15, restore_best_weights=True
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="loss", factor=0.5, patience=8, min_lr=1e-5
        ),
    ]

    model.fit(
        X_full,
        y_full,
        epochs=max_epochs,
        batch_size=32,
        callbacks=callbacks,
        class_weight=class_weights if len(classes) > 1 else None,
        verbose=1,
    )

    return model, scaler


def save_model_artifacts(model: keras.Model, scaler: StandardScaler, metadata: Dict) -> None:
    artifact = {
        "model_config": model.to_json(),
        "weights": model.get_weights(),
        "window_size": metadata["window_size"],
        "step_size": metadata["step_size"],
        "sensor_cols": sensor_cols,
        "random_state": RANDOM_STATE,
    }
    with MODEL_ARTIFACT_PATH.open("wb") as f:
        pickle.dump(artifact, f)
    with SCALER_PATH.open("wb") as f:
        pickle.dump(scaler, f)


def main():
    df = load_clean_data()
    participants = sorted(df["participant_id"].unique())
    label_by_pid = {
        pid: int(df[df["participant_id"] == pid]["label"].iloc[0]) for pid in participants
    }
    data_by_pid = {
        pid: df[df["participant_id"] == pid][sensor_cols].to_numpy(dtype=np.float32)
        for pid in participants
    }

    window_size = 64
    step_size = 16
    max_epochs = 100

    print("=== Đánh giá Leave-One-Group-Out để chọn fold tốt nhất ===")
    fold_metrics, best_fold = evaluate_logo_folds(
        df,
        data_by_pid,
        label_by_pid,
        window_size,
        step_size,
        max_epochs,
    )
    metrics_df = pd.DataFrame(fold_metrics)
    metrics_path = OUTPUT_DIR / "logo_fold_metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(metrics_df)
    print(f"\nFold tốt nhất theo F1: Fold {best_fold['fold_idx']} (F1={best_fold['metric']:.4f})")

    print("\n=== Huấn luyện lại trên toàn bộ dữ liệu ===")
    best_model, scaler = train_full_model(
        participants,
        data_by_pid,
        label_by_pid,
        window_size,
        step_size,
        max_epochs,
    )

    save_model_artifacts(
        best_model,
        scaler,
        metadata={"window_size": window_size, "step_size": step_size},
    )

    print(f"\nĐã lưu mô hình vào: {MODEL_ARTIFACT_PATH}")
    print(f"Đã lưu scaler vào: {SCALER_PATH}")
    print(f"Bảng metric từng fold: {metrics_path}")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    main()
