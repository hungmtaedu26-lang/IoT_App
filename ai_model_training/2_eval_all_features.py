import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import (
    GroupShuffleSplit,
    StratifiedKFold,
    StratifiedShuffleSplit,
    GridSearchCV,
    learning_curve,
)
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
    confusion_matrix,
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from lightgbm import early_stopping as lgb_early_stopping
from catboost import CatBoostClassifier

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DATA_FOLDER = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "evaluation_results", "all_features")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def plot_learning_curve_sklearn(estimator, X, y, cv, model_name, output_path):
    train_sizes, train_scores, val_scores = learning_curve(
        estimator,
        X,
        y,
        cv=cv,
        scoring="accuracy",
        train_sizes=np.linspace(0.4, 1.0, 5),
        n_jobs=-1,
        shuffle=True,
        random_state=42,
    )
    plt.figure(figsize=(7, 5))
    plt.plot(train_sizes, train_scores.mean(axis=1), label="Train Accuracy")
    plt.plot(train_sizes, val_scores.mean(axis=1), label="CV Accuracy")
    plt.title(f"{model_name} – Learning Curve")
    plt.xlabel("Training Samples")
    plt.ylabel("Accuracy")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_booster_history(model_name, history, output_path):
    if not history or not isinstance(history, dict):
        return

    metric_groups = list(history.keys())
    if len(metric_groups) < 2:
        return

    train_key, valid_key = metric_groups[0], metric_groups[1]
    train_metrics = history.get(train_key)
    valid_metrics = history.get(valid_key)

    if not isinstance(train_metrics, dict) or not isinstance(valid_metrics, dict):
        return

    common_metrics = [m for m in train_metrics if m in valid_metrics]
    if not common_metrics:
        common_metrics = list(train_metrics.keys())
    if not common_metrics:
        return

    def resolve_metric(candidates):
        for cand in candidates:
            for key in common_metrics:
                if key.lower() == cand.lower():
                    return key
        return None

    loss_metric = resolve_metric(["logloss", "binary_logloss", "loss"])
    if not loss_metric:
        loss_metric = common_metrics[0]

    score_metric = resolve_metric(["accuracy", "auc", "binary_error", "rmse"])
    if score_metric == loss_metric:
        score_metric = None
    if not score_metric and len(common_metrics) > 1:
        score_metric = common_metrics[1]

    n_plots = 2 if score_metric else 1
    plt.figure(figsize=(12, 5))
    plot_index = 1

    if loss_metric:
        plt.subplot(1, n_plots, plot_index)
        plt.plot(train_metrics[loss_metric], label=f"{train_key} {loss_metric}")
        plt.plot(valid_metrics[loss_metric], label=f"{valid_key} {loss_metric}")
        plt.title(f"{model_name} - {loss_metric}")
        plt.xlabel("Iterations")
        plt.ylabel(loss_metric)
        plt.legend()
        plot_index += 1

    if score_metric:
        plt.subplot(1, n_plots, plot_index)
        plt.plot(train_metrics[score_metric], label=f"{train_key} {score_metric}")
        plt.plot(valid_metrics[score_metric], label=f"{valid_key} {score_metric}")
        plt.title(f"{model_name} - {score_metric}")
        plt.xlabel("Iterations")
        plt.ylabel(score_metric)
        plt.legend()

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_confusion(y_true, y_pred, model_name, output_path):
    cm = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Non-MDD", "MDD"],
        yticklabels=["Non-MDD", "MDD"],
    )
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title(f"Confusion Matrix - {model_name}")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def prepare_data():
    data_path = os.path.join(PROCESSED_DATA_FOLDER, "features.csv")
    df = pd.read_csv(data_path)
    df = df.fillna(df.mean(numeric_only=True))
    feature_cols = [c for c in df.columns if c not in ("participant_id", "label")]
    X = df[feature_cols]
    y = df["label"]
    groups = df["participant_id"]
    return X, y, groups


def stratified_group_split(X, y, groups):
    splitter = GroupShuffleSplit(test_size=0.3, n_splits=1, random_state=42)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    return (
        X.iloc[train_idx],
        X.iloc[test_idx],
        y.iloc[train_idx],
        y.iloc[test_idx],
        groups.iloc[train_idx],
        groups.iloc[test_idx],
    )


def build_models():
    return {
        "Logistic Regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=42,
                        solver="liblinear",
                    ),
                ),
            ]
        ),
        "Random Forest": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    RandomForestClassifier(
                        random_state=42, class_weight="balanced_subsample"
                    ),
                ),
            ]
        ),
        "XGBoost": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    XGBClassifier(
                        eval_metric=["logloss", "auc"],
                        use_label_encoder=False,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "LightGBM": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LGBMClassifier(
                        class_weight="balanced", random_state=42, verbosity=-1
                    ),
                ),
            ]
        ),
        "CatBoost": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    CatBoostClassifier(
                        verbose=False,
                        random_state=42,
                        auto_class_weights="Balanced",
                        allow_writing_files=False,
                    ),
                ),
            ]
        ),
    }


def build_param_grid():
    return {
        "Logistic Regression": {"model__C": [0.01, 0.1, 1, 10]},
        "Random Forest": {
            "model__n_estimators": [100, 200, 400],
            "model__max_depth": [4, 6, 10],
        },
        "XGBoost": {
            "model__n_estimators": [100, 300],
            "model__learning_rate": [0.05, 0.1],
            "model__max_depth": [3, 5],
            "model__subsample": [0.7, 1.0],
        },
        "LightGBM": {
            "model__n_estimators": [200, 400],
            "model__learning_rate": [0.05, 0.1],
            "model__num_leaves": [15, 31],
        },
        "CatBoost": {
            "model__iterations": [300, 500],
            "model__learning_rate": [0.03, 0.08],
            "model__depth": [4, 6],
        },
    }


def refit_with_validation(best_pipeline, X_train, y_train, model_name):
    if model_name not in {"XGBoost", "LightGBM", "CatBoost"}:
        return None

    scaler = best_pipeline.named_steps["scaler"]
    base_model = best_pipeline.named_steps["model"]
    model_cls = base_model.__class__
    model_params = base_model.get_params()

    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(splitter.split(X_train, y_train))
    X_tr_scaled = scaler.fit_transform(X_train.iloc[train_idx])
    X_val_scaled = scaler.transform(X_train.iloc[val_idx])

    y_tr = y_train.iloc[train_idx]
    y_val = y_train.iloc[val_idx]

    booster = model_cls(**model_params)

    if model_name == "LightGBM":
        try:
            booster.fit(
                X_tr_scaled,
                y_tr,
                eval_set=[(X_tr_scaled, y_tr), (X_val_scaled, y_val)],
                eval_metric=["logloss", "auc"],
                callbacks=[lgb_early_stopping(50, verbose=False)],
            )
        except TypeError:
            booster.fit(
                X_tr_scaled,
                y_tr,
                eval_set=[(X_tr_scaled, y_tr), (X_val_scaled, y_val)],
                eval_metric="logloss",
                verbose=False,
            )
    elif model_name == "CatBoost":
        booster.fit(
            X_tr_scaled,
            y_tr,
            eval_set=(X_val_scaled, y_val),
            use_best_model=True,
        )
    else:  # XGBoost
        try:
            booster.set_params(early_stopping_rounds=50)
            booster.fit(
                X_tr_scaled,
                y_tr,
                eval_set=[(X_tr_scaled, y_tr), (X_val_scaled, y_val)],
                verbose=False,
            )
        except TypeError:
            booster.fit(
                X_tr_scaled,
                y_tr,
                eval_set=[(X_tr_scaled, y_tr), (X_val_scaled, y_val)],
                verbose=False,
            )

    return booster


def get_evaluation_history(booster):
    if booster is None:
        return None

    if hasattr(booster, "evals_result"):
        try:
            return booster.evals_result()
        except TypeError:
            result = booster.evals_result
            return result() if callable(result) else result

    if hasattr(booster, "evals_result_"):
        return booster.evals_result_

    if hasattr(booster, "get_evals_result"):
        return booster.get_evals_result()

    if hasattr(booster, "booster_") and hasattr(booster.booster_, "evals_result"):
        return booster.booster_.evals_result()

    return None


def evaluate_models(X_train, X_test, y_train, y_test):
    models = build_models()
    param_grid = build_param_grid()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for name, pipeline in models.items():
        print(f"\n================ {name} ================")
        grid = GridSearchCV(
            pipeline,
            param_grid[name],
            scoring="f1",
            cv=cv,
            n_jobs=-1,
            error_score="raise",
        )
        grid.fit(X_train, y_train)

        best_pipeline = grid.best_estimator_
        print("Best params:", grid.best_params_)

        y_pred = best_pipeline.predict(X_test)
        if hasattr(best_pipeline, "predict_proba"):
            y_prob = best_pipeline.predict_proba(X_test)[:, 1]
        else:
            y_prob = None

        print(classification_report(y_test, y_pred, digits=4))

        f1 = f1_score(y_test, y_pred)
        acc = accuracy_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        roc = roc_auc_score(y_test, y_prob) if y_prob is not None else np.nan

        print(
            f"Accuracy: {acc:.3f} | Precision: {prec:.3f} | "
            f"Recall: {rec:.3f} | F1: {f1:.3f} | ROC-AUC: {roc:.3f}"
        )

        cm_path = os.path.join(OUTPUT_FOLDER, f"{slugify(name)}_confusion.png")
        plot_confusion(y_test, y_pred, name, cm_path)

        lc_path = os.path.join(OUTPUT_FOLDER, f"{slugify(name)}_learning_curve.png")
        plot_learning_curve_sklearn(best_pipeline, X_train, y_train, cv, name, lc_path)

        booster = refit_with_validation(best_pipeline, X_train, y_train, name)
        if booster is not None:
            history_path = os.path.join(
                OUTPUT_FOLDER, f"{slugify(name)}_training_history.png"
            )
            history = get_evaluation_history(booster)
            if history:
                plot_booster_history(name, history, history_path)


def main():
    print("=== Evaluating models with participant-aware splits ===")
    X, y, groups = prepare_data()
    X_train, X_test, y_train, y_test, _, _ = stratified_group_split(X, y, groups)
    evaluate_models(X_train, X_test, y_train, y_test)
    print("\nAll evaluations finished; plots saved to:", OUTPUT_FOLDER)


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    main()
