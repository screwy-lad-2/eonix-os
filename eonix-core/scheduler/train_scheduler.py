#!/usr/bin/env python3
"""Train Eonix Scheduler LightGBM model with Optuna and export ONNX."""

from __future__ import annotations

import argparse
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, top_k_accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OrdinalEncoder


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "datasets" / "scheduler" / "feature_matrix_v2.parquet"
MODELS_DIR = REPO_ROOT / "models" / "onnx"
RESULTS_DIR = REPO_ROOT / "results"


def _require_training_deps() -> None:
    missing = []
    for pkg in ["lightgbm", "optuna", "onnxmltools", "onnxruntime", "skl2onnx"]:
        try:
            __import__(pkg)
        except Exception:
            missing.append(pkg)
    if missing:
        raise RuntimeError(
            "Missing dependencies: " + ", ".join(missing) +
            ". Install with: pip install lightgbm optuna onnxmltools onnxruntime skl2onnx"
        )


def load_feature_data(path: Path = DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Feature matrix not found: {path}")
    return pd.read_parquet(path)


def prepare_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str], OrdinalEncoder, LabelEncoder]:
    work = df.copy()
    counts = work["next_process_name"].astype(str).value_counts()
    keep = counts[counts >= 3].index
    work = work[work["next_process_name"].astype(str).isin(keep)].reset_index(drop=True)
    if work.empty:
        raise ValueError("No classes have enough samples after filtering rare targets (<3 rows).")

    feature_cols = [c for c in df.columns if c.startswith("prev_") or c in {
        "hour_of_day", "day_of_week", "is_weekend", "cpu_pressure", "ram_pressure",
        "ppid", "pid_mod_10", "launch_burst_5m"
    }]
    if len(feature_cols) != 18:
        raise ValueError(f"Expected 18 feature columns, got {len(feature_cols)}")

    X_df = work[feature_cols].copy()
    y_raw = work["next_process_name"].astype(str)

    cat_cols = [c for c in feature_cols if c.startswith("prev_")]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    X_df[cat_cols] = enc.fit_transform(X_df[cat_cols].astype(str))
    X_df[num_cols] = X_df[num_cols].astype(float)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)
    X = X_df.values.astype(np.float32)
    return X, y, feature_cols, enc, label_encoder


def split_data(X: np.ndarray, y: np.ndarray):
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    try:
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
        )
    except ValueError:
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=0.5, random_state=42, stratify=None
        )
    return X_train, X_val, X_test, y_train, y_val, y_test


def train_with_optuna(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_trials: int,
):
    import lightgbm as lgb
    import optuna

    n_classes = len(np.unique(y_train))

    def objective(trial):
        params = {
            "objective": "multiclass",
            "num_class": n_classes,
            "metric": "multi_logloss",
            "num_leaves": trial.suggest_int("num_leaves", 20, 300),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }
        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_val)
        return float(top_k_accuracy_score(y_val, probs, k=3, labels=np.arange(n_classes)))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

    print(f"[Optuna] Best Top-3 accuracy: {study.best_value:.4f} ({n_trials} trials)")
    return study.best_params, study.best_value


def train_final_model(X_trainval: np.ndarray, y_trainval: np.ndarray, best_params: Dict):
    import lightgbm as lgb

    params = {
        "objective": "multiclass",
        "num_class": len(np.unique(y_trainval)),
        "metric": "multi_logloss",
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
        **best_params,
    }
    model = lgb.LGBMClassifier(**params)
    model.fit(X_trainval, y_trainval)
    return model


def _compact_params(best_params: Dict) -> Dict:
    compact = dict(best_params)
    compact["num_leaves"] = int(min(max(int(compact.get("num_leaves", 64)), 20), 80))
    compact["n_estimators"] = int(min(max(int(compact.get("n_estimators", 300)), 100), 500))
    compact["learning_rate"] = float(min(max(float(compact.get("learning_rate", 0.05)), 0.01), 0.2))
    return compact


def export_onnx(model, n_features: int, onnx_path: Path) -> None:
    import onnxmltools
    from onnxmltools.convert.common.data_types import FloatTensorType

    initial_types = [("input", FloatTensorType([None, n_features]))]
    onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_types)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    with onnx_path.open("wb") as f:
        f.write(onnx_model.SerializeToString())


def verify_onnx_matches_lgbm(model, onnx_path: Path, X_sample: np.ndarray, tol: float = 1e-4) -> bool:
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    lgb_probs = model.predict_proba(X_sample)
    onnx_out = session.run(None, {input_name: X_sample.astype(np.float32)})
    raw_probs = onnx_out[1]
    if isinstance(raw_probs, np.ndarray):
        onnx_probs = raw_probs
    elif isinstance(raw_probs, list) and raw_probs and isinstance(raw_probs[0], dict):
        classes = [int(c) for c in model.classes_]
        onnx_probs = np.array(
            [[float(row.get(c, 0.0)) for c in classes] for row in raw_probs],
            dtype=np.float32,
        )
    else:
        onnx_probs = np.array(raw_probs, dtype=np.float32)

    return np.allclose(lgb_probs, onnx_probs, atol=tol, rtol=tol)


def run_training(
    trials: int = 30,
    version: str = "v1.0",
    data_path: Path | None = None,
    models_dir: Path | None = None,
    results_dir: Path | None = None,
) -> Dict:
    _require_training_deps()

    local_data_path = data_path or DATA_PATH
    local_models_dir = models_dir or MODELS_DIR
    local_results_dir = results_dir or RESULTS_DIR

    df = load_feature_data(local_data_path)
    X, y, feature_cols, feat_encoder, label_encoder = prepare_xy(df)
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(X, y)

    best_params, _ = train_with_optuna(X_train, y_train, X_val, y_val, n_trials=trials)

    X_trainval = np.vstack([X_train, X_val])
    y_trainval = np.concatenate([y_train, y_val])
    model = train_final_model(X_trainval, y_trainval, best_params)

    probs = model.predict_proba(X_test)
    preds = np.argmax(probs, axis=1)
    top1 = float((preds == y_test).mean())
    top3 = float(top_k_accuracy_score(y_test, probs, k=3, labels=model.classes_))
    report = classification_report(
        y_test,
        preds,
        output_dict=True,
        zero_division=0,
    )

    local_models_dir.mkdir(parents=True, exist_ok=True)
    local_results_dir.mkdir(parents=True, exist_ok=True)

    onnx_path = local_models_dir / "scheduler.onnx"
    label_path = local_models_dir / "label_encoder.pkl"
    feat_enc_path = local_models_dir / "feature_encoder.pkl"
    meta_path = local_models_dir / "model_metadata.json"
    train_report_path = local_results_dir / "scheduler_training_report.json"

    used_params = dict(best_params)
    try:
        export_onnx(model, n_features=X.shape[1], onnx_path=onnx_path)
    except Exception as exc:
        fallback = _compact_params(best_params)
        print(f"[ONNX fallback] conversion failed with best params ({exc.__class__.__name__}).")
        print(f"[ONNX fallback] retraining compact model for export: {fallback}")
        model = train_final_model(X_trainval, y_trainval, fallback)
        used_params = fallback
        export_onnx(model, n_features=X.shape[1], onnx_path=onnx_path)
    with label_path.open("wb") as f:
        pickle.dump(label_encoder, f)
    with feat_enc_path.open("wb") as f:
        pickle.dump({"encoder": feat_encoder, "feature_cols": feature_cols}, f)

    onnx_ok = verify_onnx_matches_lgbm(model, onnx_path, X_test[:10])

    feature_importances = {
        name: float(val) for name, val in zip(feature_cols, model.feature_importances_)
    }
    metadata = {
        "version": version,
        "top1": top1,
        "top3": top3,
        "n_samples": int(len(df)),
        "n_classes": int(len(np.unique(y))),
        "best_params": used_params,
        "trained_date": datetime.now(timezone.utc).isoformat(),
        "auto_retrain_at": 60000,
        "feature_columns": feature_cols,
        "onnx_verified": bool(onnx_ok),
    }
    train_report = {
        **metadata,
        "per_class_f1": {
            str(label_encoder.inverse_transform([int(k)])[0]): float(v["f1-score"])
            for k, v in report.items()
            if isinstance(v, dict) and "f1-score" in v and str(k).isdigit()
        },
        "feature_importances": feature_importances,
    }

    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    train_report_path.write_text(json.dumps(train_report, indent=2), encoding="utf-8")

    print(f"Top-1: {top1*100:.2f}% | Top-3: {top3*100:.2f}%")
    print("ONNX verified ✅" if onnx_ok else "ONNX verified ❌")
    print(f"{version} saved -> {onnx_path}")

    return {
        "top1": top1,
        "top3": top3,
        "onnx_ok": onnx_ok,
        "onnx_path": str(onnx_path),
        "metadata_path": str(meta_path),
        "label_path": str(label_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train scheduler LightGBM model")
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--version", type=str, default="v1.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_training(trials=args.trials, version=args.version)


if __name__ == "__main__":
    main()


def _tiny_synth_matrix(rows: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    classes = np.array(["chrome.exe", "code.exe", "python.exe", "explorer.exe"])
    base = []
    for i in range(rows):
        c = classes[i % len(classes)]
        base.append({
            "hour_of_day": i % 24,
            "day_of_week": i % 7,
            "is_weekend": 1 if (i % 7) in (5, 6) else 0,
            "cpu_pressure": float((i % 10) / 10.0),
            "ram_pressure": float((i % 8) / 10.0),
            "ppid": int(100 + (i % 20)),
            "pid_mod_10": int(i % 10),
            "launch_burst_5m": int(i % 5),
            **{f"prev_{k}": classes[(i - k) % len(classes)] for k in range(1, 11)},
            "next_process_name": c,
            "timestamp": float(1700000000 + i),
            "pid": int(1000 + i),
            "proc_name": c,
        })
    df = pd.DataFrame(base)
    df["cpu_pressure"] += rng.normal(0, 0.01, size=len(df))
    df["ram_pressure"] += rng.normal(0, 0.01, size=len(df))
    return df


def test_model_top3_above_40_percent(tmp_path):
    df = _tiny_synth_matrix(800)
    local_data = tmp_path / "feature_matrix_v2.parquet"
    df.to_parquet(local_data, index=False)
    out = run_training(
        trials=3,
        version="vtest",
        data_path=local_data,
        models_dir=tmp_path / "models",
        results_dir=tmp_path / "results",
    )
    assert out["top3"] > 0.40


def test_onnx_file_exists_after_training(tmp_path):
    df = _tiny_synth_matrix(500)
    local_data = tmp_path / "feature_matrix_v2.parquet"
    df.to_parquet(local_data, index=False)
    out = run_training(
        trials=2,
        version="vtest",
        data_path=local_data,
        models_dir=tmp_path / "models",
        results_dir=tmp_path / "results",
    )
    assert Path(out["onnx_path"]).exists()


def test_onnx_output_matches_lgbm(tmp_path):
    df = _tiny_synth_matrix(600)
    local_data = tmp_path / "feature_matrix_v2.parquet"
    df.to_parquet(local_data, index=False)
    out = run_training(
        trials=2,
        version="vtest",
        data_path=local_data,
        models_dir=tmp_path / "models",
        results_dir=tmp_path / "results",
    )
    assert out["onnx_ok"] is True


def test_label_encoder_covers_all_classes(tmp_path):
    df = _tiny_synth_matrix(700)
    local_data = tmp_path / "feature_matrix_v2.parquet"
    df.to_parquet(local_data, index=False)
    out = run_training(
        trials=2,
        version="vtest",
        data_path=local_data,
        models_dir=tmp_path / "models",
        results_dir=tmp_path / "results",
    )
    with Path(out["label_path"]).open("rb") as f:
        le = pickle.load(f)
    expected = set(df["next_process_name"].astype(str).value_counts()[lambda s: s >= 3].index)
    assert set(le.classes_) == expected
