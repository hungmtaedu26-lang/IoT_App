import os
import warnings
from collections import defaultdict
from itertools import product
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.base import clone
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler
from sklearn.utils import check_random_state
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.linear_model import SGDClassifier


warnings.filterwarnings("ignore")

# --- ĐỊNH NGHĨA CÁC ĐƯỜNG DẪN THƯ MỤC ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DATA_FOLDER = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "evaluation_results", "method2")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
CONFUSION_DIR = os.path.join(OUTPUT_FOLDER, "confusion_matrices")
os.makedirs(CONFUSION_DIR, exist_ok=True)

RANDOM_STATE = 42
THRESHOLD = 0.5  # Ngưỡng sau khi hiệu chỉnh (Platt scaling) sẽ dùng 0.5

sensor_cols = ["accel_x", "temperature", "pulse_rate", "spo2"]


def build_models() -> Dict[str, object]:
    return {
        "Logistic Regression": LogisticRegression(
            max_iter=300, solver="liblinear", class_weight="balanced", random_state=RANDOM_STATE
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=5,
            random_state=RANDOM_STATE,
            class_weight="balanced_subsample",
            n_jobs=-1,
        ),
        "KNN": KNeighborsClassifier(n_neighbors=5, weights="distance"),
        "SVM": SVC(
            kernel="linear",
            C=1.0,
            probability=True,
            random_state=RANDOM_STATE,
            class_weight="balanced",
        ),
        "SGD": SGDClassifier(
            loss="log_loss",
            penalty="l2",
            max_iter=500,
            alpha=1e-4,
            random_state=RANDOM_STATE,
            class_weight="balanced",
        ),
    }


MODEL_PARAM_GRID: Dict[str, Dict[str, Iterable]] = {
    "Logistic Regression": {"C": [0.1, 1.0, 10.0]},
    "Random Forest": {"n_estimators": [200, 300, 400], "max_depth": [4, 6, 8]},
    "KNN": {"n_neighbors": [3, 5, 7]},
    "SVM": {"C": [0.1, 1.0, 10.0]},
    "SGD": {"alpha": [1e-5, 1e-4, 5e-4]},
}


def expand_param_grid(param_options: Dict[str, Iterable]) -> List[Dict[str, object]]:
    if not param_options:
        return [{}]
    keys = list(param_options.keys())
    values_product = list(product(*[param_options[k] for k in keys]))
    return [dict(zip(keys, values)) for values in values_product]


def aggregate_by_participant(
    probs: np.ndarray, labels: np.ndarray, participants: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    df_temp = pd.DataFrame(
        {"participant_id": participants, "prob": probs, "label": labels}
    )
    grouped = df_temp.groupby("participant_id")
    ordered_pids = grouped["label"].count().index.to_numpy()
    agg_probs = grouped["prob"].mean().reindex(ordered_pids).to_numpy()
    agg_labels = grouped["label"].first().reindex(ordered_pids).astype(int).to_numpy()
    return ordered_pids, agg_probs, agg_labels


def compute_classification_metrics(
    y_true: np.ndarray, probs: np.ndarray, threshold: float = THRESHOLD
) -> Dict[str, float]:
    preds = (probs >= threshold).astype(int)
    metrics = {
        "Accuracy": accuracy_score(y_true, preds),
        "F1": f1_score(y_true, preds, zero_division=0),
        "Brier Score": brier_score_loss(y_true, probs),
        "Log Loss": log_loss(y_true, np.column_stack([1 - probs, probs]), labels=[0, 1]),
    }
    try:
        metrics["ROC AUC"] = roc_auc_score(y_true, probs)
    except ValueError:
        metrics["ROC AUC"] = np.nan
    try:
        metrics["Average Precision"] = average_precision_score(y_true, probs)
    except ValueError:
        metrics["Average Precision"] = np.nan
    return metrics


def bootstrap_confidence_intervals(
    y_true: np.ndarray,
    probs: np.ndarray,
    threshold: float = THRESHOLD,
    n_bootstrap: int = 500,
    random_state: int = RANDOM_STATE,
) -> Dict[str, Tuple[float, float]]:
    rng = check_random_state(random_state)
    metrics_samples = defaultdict(list)
    if len(y_true) == 0:
        return {}

    for _ in range(n_bootstrap):
        indices = rng.randint(0, len(y_true), len(y_true))
        y_sample = y_true[indices]
        probs_sample = probs[indices]
        preds_sample = (probs_sample >= threshold).astype(int)

        metrics_samples["Accuracy"].append(accuracy_score(y_sample, preds_sample))
        metrics_samples["F1"].append(f1_score(y_sample, preds_sample, zero_division=0))

        try:
            metrics_samples["ROC AUC"].append(roc_auc_score(y_sample, probs_sample))
        except ValueError:
            metrics_samples["ROC AUC"].append(np.nan)

        try:
            metrics_samples["Average Precision"].append(
                average_precision_score(y_sample, probs_sample)
            )
        except ValueError:
            metrics_samples["Average Precision"].append(np.nan)

    ci = {}
    for metric, values in metrics_samples.items():
        arr = np.array(values, dtype=float)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            continue
        lower, upper = np.percentile(arr, [2.5, 97.5])
        ci[metric] = (float(lower), float(upper))
    return ci


def fit_platt_scaler(probs: np.ndarray, labels: np.ndarray) -> Optional[LogisticRegression]:
    if np.unique(labels).size < 2:
        return None
    try:
        calibrator = LogisticRegression(
            solver="lbfgs",
            penalty=None,
            max_iter=1000,
        )
    except ValueError:
        calibrator = LogisticRegression(
            solver="lbfgs", C=1e6, max_iter=1000
        )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        calibrator.fit(probs.reshape(-1, 1), labels)
    return calibrator


def tune_model_with_group_cv(
    model_name: str,
    base_model,
    param_grid: Dict[str, Iterable],
    X_train: pd.DataFrame,
    y_train: pd.Series,
    train_groups: pd.Series,
) -> Tuple[Dict[str, object], Optional[LogisticRegression]]:
    unique_groups = np.unique(train_groups)
    if len(unique_groups) < 3:
        # Không đủ participant để GroupKFold, giữ nguyên tham số và bỏ hiệu chỉnh
        return {}, None

    candidate_params = expand_param_grid(param_grid)
    n_splits = min(5, len(unique_groups))
    gkf = GroupKFold(n_splits=n_splits)

    best_params: Dict[str, object] = {}
    best_score = -np.inf
    best_oof_probs = None

    for params in candidate_params:
        candidate = clone(base_model)
        candidate.set_params(**params)

        oof_probs = np.zeros(len(X_train), dtype=float)

        for inner_train_idx, inner_val_idx in gkf.split(
            X_train, y_train, groups=train_groups
        ):
            X_tr = X_train.iloc[inner_train_idx]
            y_tr = y_train.iloc[inner_train_idx]
            X_val = X_train.iloc[inner_val_idx]
            y_val = y_train.iloc[inner_val_idx]

            imputer = SimpleImputer(strategy="median")
            imputer.fit(X_tr)
            X_tr_imp = imputer.transform(X_tr)
            X_val_imp = imputer.transform(X_val)

            scaler = StandardScaler()
            scaler.fit(X_tr_imp)
            X_tr_scaled = scaler.transform(X_tr_imp)
            X_val_scaled = scaler.transform(X_val_imp)

            candidate.fit(X_tr_scaled, y_tr)
            val_probs = candidate.predict_proba(X_val_scaled)[:, 1]
            oof_probs[inner_val_idx] = val_probs

        pids, agg_probs, agg_labels = aggregate_by_participant(
            oof_probs, y_train.to_numpy(), train_groups.to_numpy()
        )
        preds = (agg_probs >= THRESHOLD).astype(int)
        score = f1_score(agg_labels, preds, zero_division=0)

        if score > best_score:
            best_score = score
            best_params = params
            best_oof_probs = oof_probs

    calibrator = (
        fit_platt_scaler(best_oof_probs, y_train.to_numpy())
        if best_oof_probs is not None
        else None
    )
    return best_params, calibrator


def plot_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, model_name: str, output_path: str) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    plt.figure(figsize=(6, 4))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Không MDD (0)", "MDD (1)"],
        yticklabels=["Không MDD (0)", "MDD (1)"],
    )
    plt.title(f"Ma trận nhầm lẫn (LOGO) - {model_name}")
    plt.xlabel("Dự đoán")
    plt.ylabel("Thực tế")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def main():
    print("Bắt đầu Chương trình 3: Đánh giá Phương pháp 2 (LOGO cải tiến)")

    data_path = os.path.join(PROCESSED_DATA_FOLDER, "cleaned_sensor_data.csv")
    try:
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"[LỖI] Không tìm thấy tệp: {data_path}")
        print("Vui lòng chạy '1_preprocess_data.py' trước.")
        return

    df = df.dropna(subset=sensor_cols + ["label", "participant_id"]).copy()
    for col in sensor_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=sensor_cols)
    df["label"] = df["label"].astype(int)

    X = df[sensor_cols]
    y = df["label"]
    groups = df["participant_id"]
    participants = sorted(groups.unique())
    print(f"Tổng số participant: {len(participants)}")

    models = build_models()

    logo = LeaveOneGroupOut()

    overall_results = []
    per_subject_records = []
    per_fold_records = defaultdict(list)
    prob_storage: Dict[str, Dict[str, float]] = {
        model_name: {} for model_name in models
    }

    for fold_idx, (train_idx, test_idx) in enumerate(
        logo.split(X, y, groups=groups), start=1
    ):
        print(f"\n=== Fold {fold_idx}/{len(participants)} ===")
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        train_groups = groups.iloc[train_idx]
        test_groups = groups.iloc[test_idx]

        for model_name, base_model in models.items():
            print(f"- Đang xử lý mô hình: {model_name}")
            param_grid = MODEL_PARAM_GRID.get(model_name, {})

            best_params, calibrator = tune_model_with_group_cv(
                model_name, base_model, param_grid, X_train, y_train, train_groups
            )
            tuned_model = clone(base_model)
            if best_params:
                tuned_model.set_params(**best_params)

            imputer = SimpleImputer(strategy="median")
            imputer.fit(X_train)
            X_train_imp = imputer.transform(X_train)
            X_test_imp = imputer.transform(X_test)

            scaler = StandardScaler()
            scaler.fit(X_train_imp)
            X_train_scaled = scaler.transform(X_train_imp)
            X_test_scaled = scaler.transform(X_test_imp)

            tuned_model.fit(X_train_scaled, y_train)
            test_probs_raw = tuned_model.predict_proba(X_test_scaled)[:, 1]

            if calibrator is not None:
                test_probs = calibrator.predict_proba(test_probs_raw.reshape(-1, 1))[:, 1]
            else:
                test_probs = test_probs_raw

            pid_prob_map: Dict[str, List[float]] = defaultdict(list)
            for prob, pid in zip(test_probs, test_groups):
                pid_prob_map[pid].append(float(prob))

            fold_participants = sorted(pid_prob_map.keys())
            aggregated_probs = np.array(
                [np.mean(pid_prob_map[pid]) for pid in fold_participants], dtype=float
            )
            y_true_fold = np.array(
                [y_test[test_groups == pid].iloc[0] for pid in fold_participants], dtype=int
            )
            preds_fold = (aggregated_probs >= THRESHOLD).astype(int)

            for pid, prob, pred, true_label in zip(
                fold_participants, aggregated_probs, preds_fold, y_true_fold
            ):
                prob_storage[model_name][pid] = prob
                per_subject_records.append(
                    {
                        "model": model_name,
                        "fold": fold_idx,
                        "participant_id": pid,
                        "probability": prob,
                        "prediction": int(pred),
                        "true_label": int(true_label),
                        "correct": int(pred == true_label),
                        "threshold": THRESHOLD,
                        "calibrated": calibrator is not None,
                        "best_params": best_params.copy() if best_params else {},
                    }
                )

            fold_metrics = compute_classification_metrics(y_true_fold, aggregated_probs)
            per_fold_records[model_name].append(
                {
                    "fold": fold_idx,
                    "participants": len(fold_participants),
                    **fold_metrics,
                }
            )

    summary_rows = []
    for model_name in models:
        probs_dict = prob_storage[model_name]
        ordered_pids = [pid for pid in participants if pid in probs_dict]
        probs = np.array([probs_dict[pid] for pid in ordered_pids], dtype=float)
        y_true = np.array(
            [int(df[df["participant_id"] == pid]["label"].iloc[0]) for pid in ordered_pids],
            dtype=int,
        )
        preds = (probs >= THRESHOLD).astype(int)

        metrics = compute_classification_metrics(y_true, probs)
        ci = bootstrap_confidence_intervals(y_true, probs, THRESHOLD)

        summary_row = {
            "Model": model_name,
            "Accuracy": metrics["Accuracy"],
            "F1": metrics["F1"],
            "ROC AUC": metrics["ROC AUC"],
            "Average Precision": metrics["Average Precision"],
            "Brier Score": metrics["Brier Score"],
            "Log Loss": metrics["Log Loss"],
            "Accuracy 95% CI": ci.get("Accuracy"),
            "F1 95% CI": ci.get("F1"),
            "ROC AUC 95% CI": ci.get("ROC AUC"),
            "AUCPR 95% CI": ci.get("Average Precision"),
        }
        summary_rows.append(summary_row)

        report = classification_report(
            y_true,
            preds,
            target_names=["Không MDD (0)", "MDD (1)"],
            digits=4,
            zero_division=0,
        )
        report_path = os.path.join(
            OUTPUT_FOLDER, f"classification_report_{model_name.lower().replace(' ', '_')}.txt"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        cm_path = os.path.join(
            CONFUSION_DIR, f"cm_logo_{model_name.lower().replace(' ', '_')}.png"
        )
        plot_confusion_matrix(y_true, preds, model_name, cm_path)

        per_subject_df = pd.DataFrame(
            [rec for rec in per_subject_records if rec["model"] == model_name]
        )
        per_subject_path = os.path.join(
            OUTPUT_FOLDER,
            f"per_subject_metrics_{model_name.lower().replace(' ', '_')}.csv",
        )
        per_subject_df.to_csv(per_subject_path, index=False)

        fold_metrics_df = pd.DataFrame(per_fold_records[model_name])
        fold_metrics_path = os.path.join(
            OUTPUT_FOLDER,
            f"fold_metrics_{model_name.lower().replace(' ', '_')}.csv",
        )
        fold_metrics_df.to_csv(fold_metrics_path, index=False)

        print(f"\n[{model_name}]")
        print(per_subject_df.groupby("fold")["correct"].mean().describe())

    summary_df = pd.DataFrame(summary_rows).sort_values(by="F1", ascending=False)
    summary_path = os.path.join(OUTPUT_FOLDER, "logo_metrics_summary.csv")
    summary_df.to_csv(summary_path, index=False)

    print("\n=== Tổng hợp Models ===")
    print(summary_df)
    print(f"\nKết quả chi tiết lưu tại: {OUTPUT_FOLDER}")
    print(" - Bảng tổng hợp: logo_metrics_summary.csv")
    print(" - Ma trận nhầm lẫn: confusion_matrices/cm_logo_<model>.png")
    print(" - Báo cáo phân loại: classification_report_<model>.txt")
    print(" - Metrics từng participant: per_subject_metrics_<model>.csv")
    print(" - Metrics từng fold: fold_metrics_<model>.csv")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
