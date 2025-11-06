import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from numpy.random import default_rng

from sklearn.base import clone
from sklearn.model_selection import LeaveOneOut
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    roc_auc_score,
    brier_score_loss,
    log_loss,
    confusion_matrix,
    classification_report,
)
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC


warnings.filterwarnings("ignore")


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "processed" / "features_selected.csv"
OUTPUT_DIR = BASE_DIR / "evaluation_results" / "selected_features"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def augment_with_noise(
    X: pd.DataFrame,
    y: pd.Series,
    repeats: int = 2,
    gaussian_scale: float = 0.2,
    jitter_prob: float = 0.05,
    label_flip_prob: float = 0.05,
    rng: Optional[np.random.Generator] = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Augment training data with Gaussian noise, jitter, and optional label flip."""
    if rng is None:
        rng = default_rng(RANDOM_STATE)

    stds = X.std(ddof=0).replace(0, 1e-9)
    feature_frames = [X]
    label_frames = [y]

    base_values = X.to_numpy(copy=True)
    std_array = stds.to_numpy()

    for _ in range(repeats):
        noisy = base_values.copy()
        noise = rng.normal(0.0, 1.0, size=noisy.shape)
        noisy += noise * std_array * gaussian_scale

        mask = rng.random(size=noisy.shape) < jitter_prob
        jitter = rng.normal(0.0, std_array * gaussian_scale * 0.5, size=noisy.shape)
        noisy = np.where(mask, noisy + jitter, noisy)

        noisy_df = pd.DataFrame(noisy, columns=X.columns, index=X.index)

        y_noisy = y.to_numpy(copy=True)
        if label_flip_prob > 0:
            flip_mask = rng.random(len(y_noisy)) < label_flip_prob
            y_noisy[flip_mask] = 1 - y_noisy[flip_mask]

        feature_frames.append(noisy_df.reset_index(drop=True))
        label_frames.append(pd.Series(y_noisy.astype(int), name=y.name))

    X_aug = pd.concat(feature_frames, axis=0).reset_index(drop=True)
    y_aug = pd.concat(label_frames, axis=0).reset_index(drop=True)
    return X_aug, y_aug


def safe_log_loss(y_true, y_prob, eps: float = 1e-15) -> float:
    prob = np.clip(np.asarray(y_prob), eps, 1 - eps)
    if prob.ndim == 1:
        prob = np.column_stack([1 - prob, prob])
    return log_loss(y_true, prob, labels=[0, 1])


def plot_confusion(cm: np.ndarray, model_name: str, output_dir: Path) -> None:
    plt.figure(figsize=(3.6, 3.2))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Pred 0", "Pred 1"],
        yticklabels=["True 0", "True 1"],
    )
    plt.title(f"Confusion Matrix - {model_name}")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()
    plt.savefig(output_dir / f"confusion_{slugify(model_name)}.png", dpi=200)
    plt.close()


def plot_overfitting_bars(
    metric_name: str,
    train_values: Dict[str, float],
    val_values: Dict[str, float],
    output_dir: Path,
) -> None:
    models = list(train_values.keys())
    train_means = [train_values[m] for m in models]
    val_means = [val_values[m] for m in models]

    x = np.arange(len(models))
    width = 0.35

    plt.figure(figsize=(8, 4))
    plt.bar(x - width / 2, train_means, width, label="Train")
    plt.bar(x + width / 2, val_means, width, label="Validation")
    plt.xticks(x, models, rotation=20, ha="right")
    plt.ylabel(metric_name)
    plt.title(f"Train vs Validation {metric_name}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"overfitting_{slugify(metric_name)}.png", dpi=200)
    plt.close()


def plot_fold_metric_trends(
    fold_metrics: Dict[str, List[float]],
    metric_name: str,
    output_dir: Path,
) -> None:
    plt.figure(figsize=(9, 4.8))
    for model, values in fold_metrics.items():
        plt.plot(range(1, len(values) + 1), values, marker="o", label=model)
    plt.xlabel("LOOCV Fold")
    plt.ylabel(metric_name)
    plt.title(f"{metric_name} per LOOCV Fold")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"fold_{slugify(metric_name)}.png", dpi=200)
    plt.close()


def load_dataset() -> tuple[pd.DataFrame, pd.Series]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dữ liệu '{DATA_PATH}'. "
            "Hãy chạy script 1_preprocess.py để tạo features_selected.csv."
        )

    df = pd.read_csv(DATA_PATH)
    df = df.fillna(df.mean(numeric_only=True))
    X = df.drop(columns=["participant_id", "label"])
    y = df["label"].astype(int)
    return X, y


def build_models() -> dict[str, object]:
    return {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, penalty="l2", C=1.0, solver="liblinear", random_state=RANDOM_STATE
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=5,
            random_state=RANDOM_STATE,
            class_weight="balanced_subsample",
        ),
        "KNN": KNeighborsClassifier(n_neighbors=3),
        "SVM": SVC(kernel="linear", C=1.0, probability=True, random_state=RANDOM_STATE),
        "SGD": SGDClassifier(
            loss="log_loss", penalty="l2", max_iter=1000, alpha=0.0001, random_state=RANDOM_STATE
        ),
    }


def main():
    X, y = load_dataset()
    models = build_models()
    calibration_method = "isotonic"

    loo = LeaveOneOut()
    true_labels: list[int] = []
    pred_labels = {name: [] for name in models}
    pred_probs = {name: [] for name in models}

    train_metrics = {
        name: {"accuracy": [], "f1": [], "log_loss": []} for name in models
    }

    rng = default_rng(RANDOM_STATE)

    for fold_idx, (train_index, test_index) in enumerate(loo.split(X, y), start=1):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]

        fold_rng = default_rng(rng.integers(0, 1_000_000))
        X_aug, y_aug = augment_with_noise(
            X_train,
            y_train,
            repeats=2,
            gaussian_scale=0.2,
            jitter_prob=0.05,
            label_flip_prob=0.05,
            rng=fold_rng,
        )

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_aug)
        X_test_scaled = scaler.transform(X_test)
        true_label = int(y_test.iloc[0])
        true_labels.append(true_label)

        for name, base_model in models.items():
            model = clone(base_model)
            calibrator = CalibratedClassifierCV(
                model, method=calibration_method, cv=3
            )
            calibrator.fit(X_train_scaled, y_aug)

            proba = calibrator.predict_proba(X_test_scaled)[0, 1]
            pred = calibrator.predict(X_test_scaled)[0]

            pred_probs[name].append(proba)
            pred_labels[name].append(int(pred))

            train_pred = calibrator.predict(X_train_scaled)
            train_prob = calibrator.predict_proba(X_train_scaled)[:, 1]

            train_metrics[name]["accuracy"].append(accuracy_score(y_aug, train_pred))
            train_metrics[name]["f1"].append(f1_score(y_aug, train_pred, zero_division=0))
            train_metrics[name]["log_loss"].append(safe_log_loss(y_aug, train_prob))

    results = []
    confusion_matrices = {}

    for name in models:
        y_pred = np.array(pred_labels[name])
        y_proba = np.array(pred_probs[name])
        cm = confusion_matrix(true_labels, y_pred, labels=[0, 1])
        confusion_matrices[name] = cm

        metrics = {
            "Model": name,
            "Accuracy": accuracy_score(true_labels, y_pred),
            "F1": f1_score(true_labels, y_pred, zero_division=0),
            "ROC AUC": roc_auc_score(true_labels, y_proba),
            "Brier Score": brier_score_loss(true_labels, y_proba),
            "Log Loss": safe_log_loss(true_labels, y_proba),
            "Train Accuracy": np.mean(train_metrics[name]["accuracy"]),
            "Train F1": np.mean(train_metrics[name]["f1"]),
            "Train Log Loss": np.mean(train_metrics[name]["log_loss"]),
        }
        results.append(metrics)

        plot_confusion(cm, name, OUTPUT_DIR)

    results_df = pd.DataFrame(results).sort_values(by="F1", ascending=False)
    results_path = OUTPUT_DIR / "loocv_metrics_summary.csv"
    results_df.to_csv(results_path, index=False)

    print("=== Leave-One-Out Metrics (Validation) ===")
    print(results_df[["Model", "Accuracy", "F1", "ROC AUC", "Brier Score", "Log Loss"]])
    print("\n=== Training Metrics (Augmented set) ===")
    print(results_df[["Model", "Train Accuracy", "Train F1", "Train Log Loss"]])

    # Plot overfitting diagnostics
    train_f1_map = {row["Model"]: row["Train F1"] for _, row in results_df.iterrows()}
    val_f1_map = {row["Model"]: row["F1"] for _, row in results_df.iterrows()}
    train_acc_map = {row["Model"]: row["Train Accuracy"] for _, row in results_df.iterrows()}
    val_acc_map = {row["Model"]: row["Accuracy"] for _, row in results_df.iterrows()}

    plot_overfitting_bars("F1", train_f1_map, val_f1_map, OUTPUT_DIR)
    plot_overfitting_bars("Accuracy", train_acc_map, val_acc_map, OUTPUT_DIR)

    cumulative_f1: Dict[str, List[float]] = {}
    cumulative_acc: Dict[str, List[float]] = {}
    true_array = np.array(true_labels)
    for name in models:
        preds = np.array(pred_labels[name])
        fold_f1: List[float] = []
        fold_acc: List[float] = []
        for i in range(1, len(true_array) + 1):
            fold_acc.append(accuracy_score(true_array[:i], preds[:i]))
            fold_f1.append(f1_score(true_array[:i], preds[:i], zero_division=0))
        cumulative_f1[name] = fold_f1
        cumulative_acc[name] = fold_acc

    plot_fold_metric_trends(cumulative_f1, "Validation F1 (cumulative)", OUTPUT_DIR)
    plot_fold_metric_trends(cumulative_acc, "Validation Accuracy (cumulative)", OUTPUT_DIR)

    # Save classification reports
    report_path = OUTPUT_DIR / "classification_reports.txt"
    with report_path.open("w", encoding="utf-8") as f:
        for name in models:
            y_pred = np.array(pred_labels[name])
            report = classification_report(true_labels, y_pred, digits=4, zero_division=0)
            f.write(f"===== {name} =====\n")
            f.write(report)
            f.write("\n\n")

    print(f"\nKết quả chi tiết và hình ảnh lưu tại: {OUTPUT_DIR}")
    print(f" - Bảng tổng hợp: {results_path.name}")
    print(" - Ma trận nhầm lẫn: confusion_<model>.png")
    print(" - Biểu đồ overfitting: overfitting_f1.png, overfitting_accuracy.png")
    print(" - Xu hướng F1 theo fold: fold_validation_f1.png")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    main()
