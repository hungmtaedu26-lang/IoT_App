import os
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
except ImportError as exc:  # pragma: no cover - informative error if tf missing
    raise ImportError(
        "TensorFlow chưa được cài đặt. Vui lòng thêm 'tensorflow' vào requirements "
        "và cài đặt trước khi chạy method3.py."
    ) from exc

from sklearn.model_selection import LeaveOneGroupOut, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.utils import class_weight


RANDOM_STATE = 42
np.random.seed(RANDOM_STATE)
tf.random.set_seed(RANDOM_STATE)


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "processed" / "cleaned_sensor_data.csv"
OUTPUT_DIR = BASE_DIR / "evaluation_results" / "method3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CONFUSION_DIR = OUTPUT_DIR / "confusion_matrices"
CONFUSION_DIR.mkdir(parents=True, exist_ok=True)

CURVE_DIR = OUTPUT_DIR / "training_curves"
CURVE_DIR.mkdir(parents=True, exist_ok=True)

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


def plot_confusion(y_true: np.ndarray, y_pred: np.ndarray, path: Path) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    plt.figure(figsize=(4.8, 4.0))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Pred 0", "Pred 1"],
        yticklabels=["True 0", "True 1"],
    )
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title("Confusion Matrix - CNN-LSTM")
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


def plot_history(history: keras.callbacks.History, fold: int, path: Path) -> None:
    epochs = range(1, len(history.history["loss"]) + 1)
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(epochs, history.history["loss"], label="Train Loss")
    plt.plot(epochs, history.history["val_loss"], label="Val Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title(f"Fold {fold} - Loss")
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(epochs, history.history["accuracy"], label="Train Acc")
    plt.plot(epochs, history.history["val_accuracy"], label="Val Acc")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.title(f"Fold {fold} - Accuracy")
    plt.legend()

    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


def plot_overfitting_bars(
    train_metric: List[float], val_metric: List[float], metric_name: str, path: Path
) -> None:
    folds = np.arange(1, len(train_metric) + 1)
    width = 0.35
    plt.figure(figsize=(8, 4))
    plt.bar(folds - width / 2, train_metric, width, label="Train")
    plt.bar(folds + width / 2, val_metric, width, label="Validation")
    plt.xlabel("Fold")
    plt.ylabel(metric_name)
    plt.title(f"Train vs Validation {metric_name}")
    plt.xticks(folds)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


def safe_log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    probs = np.clip(probs, 1e-10, 1 - 1e-10)
    stacked = np.column_stack([1 - probs, probs])
    return log_loss(y_true, stacked, labels=[0, 1])


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

    logo = LeaveOneGroupOut()
    groups = df["participant_id"]

    window_size = 64
    step_size = 16
    max_epochs = 100

    fold_metrics: List[Dict[str, float]] = []
    overall_probs: Dict[str, float] = {}
    overall_preds: Dict[str, int] = {}
    train_acc_collect: List[float] = []
    val_acc_collect: List[float] = []
    train_loss_collect: List[float] = []
    val_loss_collect: List[float] = []

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
            print(
                f"[Fold {fold_idx}] Không đủ dữ liệu sau khi tạo chuỗi. "
                "Bỏ qua fold này."
            )
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

        history_path = CURVE_DIR / f"fold_{fold_idx}_learning_curve.png"
        plot_history(history, fold_idx, history_path)

        best_epoch = int(np.argmin(history.history["val_loss"]))
        train_acc_collect.append(float(history.history["accuracy"][best_epoch]))
        val_acc_collect.append(float(history.history["val_accuracy"][best_epoch]))
        train_loss_collect.append(float(history.history["loss"][best_epoch]))
        val_loss_collect.append(float(history.history["val_loss"][best_epoch]))

        test_probs_seq = model.predict(X_test_seq, verbose=0).squeeze()
        if test_probs_seq.ndim == 0:
            test_probs_seq = np.array([float(test_probs_seq)])

        prob_by_pid: Dict[str, List[float]] = {}
        for prob, pid in zip(test_probs_seq, test_seq_pid):
            prob_by_pid.setdefault(pid, []).append(float(prob))

        fold_results = []
        for pid, probs in prob_by_pid.items():
            avg_prob = float(np.mean(probs))
            overall_probs[pid] = avg_prob
            overall_preds[pid] = int(avg_prob >= 0.5)
            fold_results.append((pid, avg_prob))

        y_true_fold = np.array([label_by_pid[pid] for pid, _ in fold_results])
        y_prob_fold = np.array([prob for _, prob in fold_results])
        y_pred_fold = (y_prob_fold >= 0.5).astype(int)

        fold_metrics.append(
            {
                "Fold": fold_idx,
                "Participants": len(fold_results),
                "Accuracy": accuracy_score(y_true_fold, y_pred_fold),
                "F1": f1_score(y_true_fold, y_pred_fold, zero_division=0),
                "ROC AUC": roc_auc_score(y_true_fold, y_prob_fold),
                "Brier Score": brier_score_loss(y_true_fold, y_prob_fold),
                "Log Loss": safe_log_loss(y_true_fold, y_prob_fold),
            }
        )

    if not fold_metrics:
        raise RuntimeError("Không có fold nào được đánh giá thành công.")

    fold_metrics_df = pd.DataFrame(fold_metrics)
    metrics_path = OUTPUT_DIR / "logo_cnn_lstm_metrics.csv"
    fold_metrics_df.to_csv(metrics_path, index=False)

    print("=== Kết quả từng fold (participant-level) ===")
    print(fold_metrics_df)

    overall_order = [pid for pid in participants if pid in overall_probs]
    y_true_all = np.array([label_by_pid[pid] for pid in overall_order])
    y_prob_all = np.array([overall_probs[pid] for pid in overall_order])
    y_pred_all = np.array([overall_preds[pid] for pid in overall_order])

    overall_metrics = {
        "Accuracy": accuracy_score(y_true_all, y_pred_all),
        "F1": f1_score(y_true_all, y_pred_all, zero_division=0),
        "ROC AUC": roc_auc_score(y_true_all, y_prob_all),
        "Brier Score": brier_score_loss(y_true_all, y_prob_all),
        "Log Loss": safe_log_loss(y_true_all, y_prob_all),
    }

    print("\n=== Tổng hợp toàn bộ participant ===")
    for key, value in overall_metrics.items():
        print(f"{key}: {value:.4f}")

    preds_df = pd.DataFrame(
        {
            "participant_id": overall_order,
            "true_label": y_true_all,
            "probability": y_prob_all,
            "prediction": y_pred_all,
        }
    )
    preds_path = OUTPUT_DIR / "participant_predictions.csv"
    preds_df.to_csv(preds_path, index=False)

    report = classification_report(
        y_true_all, y_pred_all, target_names=["Không MDD (0)", "MDD (1)"], digits=4
    )
    report_path = OUTPUT_DIR / "classification_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(report)

    cm_path = CONFUSION_DIR / "cm_logo_cnn_lstm.png"
    plot_confusion(y_true_all, y_pred_all, cm_path)

    acc_bar_path = OUTPUT_DIR / "overfitting_accuracy.png"
    loss_bar_path = OUTPUT_DIR / "overfitting_loss.png"
    plot_overfitting_bars(train_acc_collect, val_acc_collect, "Accuracy", acc_bar_path)
    plot_overfitting_bars(train_loss_collect, val_loss_collect, "Loss", loss_bar_path)

    print(f"\nKết quả lưu tại: {OUTPUT_DIR}")
    print(f" - Bảng metrics từng fold: {metrics_path.name}")
    print(f" - Dự đoán participant: {preds_path.name}")
    print(f" - Ma trận nhầm lẫn: {cm_path.name}")
    print(" - Đường cong huấn luyện per fold: training_curves/")
    print(" - Biểu đồ overfitting: overfitting_accuracy.png, overfitting_loss.png")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    main()
