"""Fit the runtime model, score it honestly, gate it, and export it.

Two models are fitted on log(calibrated seconds):

  baseline   ordinary least squares on the same features. The honest floor:
             runtime is close to linear in log(rows), so a straight line is
             already decent and the gradient booster has to beat it.
  model      HistGradientBoostingRegressor, which picks up the interactions
             (a sort is cheap under a limit and expensive without one; a window
             over 8M rows is not a window over 100k).

Every published prediction is out of sample. Holdout rows -- the most recent
batch, in time order -- are scored by a model that never saw them; earlier rows
by 5-fold cross-validation. The model that ships is refit on everything, which
is the model you would actually deploy.

The gate is fixed before the numbers are known: holdout MAPE <= 15% and
R2 >= 0.90 on log10 seconds. A model that misses it is still published and
still labelled FAIL, on the page and in the model card. A gate you can move
after seeing the result is not a gate.

The deployed model is exported to ONNX and checked against sklearn on every
training row before it is written, so the copy the page runs in a visitor's
browser is the copy that was scored here.
"""

import hashlib
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import onnxruntime
from skl2onnx import to_onnx
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict

from .features import FEATURES, featurise
from .workload import (
    DIM_ROW_BYTES,
    DIM_ROWS,
    FACT_ROW_BYTES,
    FACT_TABLES,
    JOIN_DIMS,
    LIMITS,
    SELECTIVITIES,
)

GATE_MAPE_PCT = 15.0
GATE_R2 = 0.90
GATE_RULE = "holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds"
HOLDOUT_FRACTION = 0.3
BOOTSTRAP_DRAWS = 2000
MIN_ROWS_TO_TRAIN = 12
SEED = 20260821

ONNX_OPSET = {"": 17, "ai.onnx.ml": 3}
ONNX_TOLERANCE = 1e-4

PREDICTION_COLUMNS = ["model_version", "query_id", "actual_seconds", "predicted_seconds",
                      "abs_pct_error", "in_holdout", "predicted_at"]
MODEL_COLUMNS = ["model_version", "trained_at", "batches_measured", "n_train_rows",
                 "n_holdout_rows", "model_kind", "holdout_mae_seconds", "holdout_mape_pct",
                 "mape_ci_low_pct", "mape_ci_high_pct", "holdout_r2", "cv_mape_pct",
                 "baseline_mape_pct", "passes_gate", "gate_rule"]


def new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error", max_iter=500, learning_rate=0.06, max_leaf_nodes=15,
        min_samples_leaf=4, l2_regularization=1.0, early_stopping=False,
        random_state=SEED)


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(predicted - actual) / actual) * 100.0)


def r_squared(actual_log: np.ndarray, predicted_log: np.ndarray) -> float:
    residual = float(np.sum((actual_log - predicted_log) ** 2))
    total = float(np.sum((actual_log - np.mean(actual_log)) ** 2))
    return 1.0 - residual / total if total > 0 else 0.0


def bootstrap_mape_ci(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    """A MAPE without a spread is a number, not a result."""
    errors = np.abs(predicted - actual) / actual * 100.0
    rng = np.random.default_rng(SEED)
    draws = rng.choice(errors, size=(BOOTSTRAP_DRAWS, errors.size), replace=True).mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def passes_gate(holdout_mape_pct: float, holdout_r2: float) -> bool:
    return bool(holdout_mape_pct <= GATE_MAPE_PCT and holdout_r2 >= GATE_R2)


def split(rows: list[dict]) -> tuple[list[int], list[int]]:
    """Time-ordered holdout: the most recent batch, or the tail of the only one."""
    batches = sorted({row["batch_name"] for row in rows})
    if len(batches) > 1:
        last = batches[-1]
        holdout = [i for i, row in enumerate(rows) if row["batch_name"] == last]
    else:
        cut = int(len(rows) * (1 - HOLDOUT_FRACTION))
        holdout = list(range(cut, len(rows)))
    train = [i for i in range(len(rows)) if i not in set(holdout)]
    return train, holdout


def calibration_table(actual: np.ndarray, predicted: np.ndarray) -> list[dict]:
    """Is the model wrong evenly, or only at one end? Deciles of predicted runtime."""
    order = np.argsort(predicted)
    buckets = np.array_split(order, min(10, max(1, len(order) // 4)))
    table = []
    for number, bucket in enumerate(buckets, start=1):
        if not bucket.size:
            continue
        table.append({
            "decile": number, "queries": int(bucket.size),
            "predicted_seconds": round(float(np.mean(predicted[bucket])), 4),
            "actual_seconds": round(float(np.mean(actual[bucket])), 4),
            "abs_pct_error": round(mape(actual[bucket], predicted[bucket]), 2),
        })
    return table


def version_for(rows: list[dict], history: list[dict]) -> str:
    """Sequence number plus a digest of the measurements it was trained on."""
    digest = hashlib.sha256(
        "|".join(f"{row['query_id']}:{row['median_seconds']}" for row in rows).encode()
    ).hexdigest()[:8]
    return f"v{len(history) + 1}-{digest}"


def fit(rows: list[dict], history: list[dict] | None = None) -> dict:
    """Fit, score out of sample, gate. Returns metrics, predictions and the model.

    Nothing is written here. The caller decides what to publish, which is what
    makes this testable on a handful of synthetic rows.
    """
    if len(rows) < MIN_ROWS_TO_TRAIN:
        raise ValueError(f"{len(rows)} measured queries: need at least {MIN_ROWS_TO_TRAIN}")
    history = history or []

    features = featurise(rows)
    actual = np.array([float(row["normalized_seconds"]) for row in rows])
    actual_log = np.log(actual)
    train_index, holdout_index = split(rows)

    model = new_model().fit(features[train_index], actual_log[train_index])
    baseline = LinearRegression().fit(features[train_index], actual_log[train_index])

    holdout_predicted = np.exp(model.predict(features[holdout_index]))
    holdout_actual = actual[holdout_index]
    baseline_predicted = np.exp(baseline.predict(features[holdout_index]))

    folds = KFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_predicted = np.exp(cross_val_predict(new_model(), features[train_index],
                                            actual_log[train_index], cv=folds))

    ci_low, ci_high = bootstrap_mape_ci(holdout_actual, holdout_predicted)
    holdout_mape = mape(holdout_actual, holdout_predicted)
    holdout_r2 = r_squared(np.log10(holdout_actual), np.log10(holdout_predicted))

    importance = permutation_importance(model, features[holdout_index],
                                        actual_log[holdout_index], n_repeats=15,
                                        random_state=SEED, scoring="neg_mean_absolute_error")
    importances = sorted(
        [{"feature": name, "importance": round(float(value), 4)}
         for name, value in zip(FEATURES, importance.importances_mean, strict=True)],
        key=lambda item: item["importance"], reverse=True)

    version = version_for(rows, history)
    trained_at = datetime.now(UTC).isoformat(timespec="seconds")
    batches = sorted({row["batch_name"] for row in rows})
    reps = [int(row["reps"]) for row in rows]

    metrics = {
        "model_version": version, "trained_at": trained_at,
        "batches_measured": len(batches), "batches": batches,
        "n_train_rows": len(train_index), "n_holdout_rows": len(holdout_index),
        "model_kind": "HistGradientBoostingRegressor(log seconds)",
        "holdout_mae_seconds": round(float(np.mean(np.abs(
            holdout_predicted - holdout_actual))), 5),
        "holdout_mape_pct": round(holdout_mape, 3),
        "mape_ci_low_pct": round(ci_low, 3), "mape_ci_high_pct": round(ci_high, 3),
        "holdout_r2": round(holdout_r2, 4),
        "cv_mape_pct": round(mape(actual[train_index], cv_predicted), 3),
        "baseline_mape_pct": round(mape(holdout_actual, baseline_predicted), 3),
        "passes_gate": passes_gate(holdout_mape, holdout_r2), "gate_rule": GATE_RULE,
        "gate_mape_pct": GATE_MAPE_PCT, "gate_r2": GATE_R2,
        "cpu_count": int(rows[-1]["cpu_count"]),
        "duckdb_threads": int(rows[-1]["duckdb_threads"]),
        "reps_median": int(np.median(reps)),
        "runtime_min_seconds": float(np.min(actual)),
        "runtime_max_seconds": float(np.max(actual)),
        "runtime_median_seconds": float(np.median(actual)),
        "machine_factor_min": float(min(float(row["machine_factor"]) for row in rows)),
        "machine_factor_max": float(max(float(row["machine_factor"]) for row in rows)),
        "importances": importances,
        "calibration": calibration_table(holdout_actual, holdout_predicted),
    }

    holdout_set = set(holdout_index)
    predicted = np.empty_like(actual)
    predicted[holdout_index] = holdout_predicted
    predicted[train_index] = cv_predicted
    prediction_rows = [{
        "model_version": version, "query_id": row["query_id"],
        "actual_seconds": round(float(actual[i]), 6),
        "predicted_seconds": round(float(predicted[i]), 6),
        "abs_pct_error": round(float(abs(predicted[i] - actual[i]) / actual[i] * 100.0), 3),
        "in_holdout": 1 if i in holdout_set else 0,
        "predicted_at": trained_at,
    } for i, row in enumerate(rows)]

    deployed = new_model().fit(features, actual_log)
    return {"metrics": metrics, "predictions": prediction_rows, "model": deployed,
            "features": features}


def export_onnx(model, features: np.ndarray, metrics: dict,
                onnx_path: Path, meta_path: Path) -> float:
    """Ship the deployed model to the page, plus what a caller needs to use it.

    The page runs this file in the visitor's browser through onnxruntime-web, so
    the export carries the feature order, the transforms, the training envelope
    and the published error: everything needed to turn seven knobs into a number
    and to say how much to trust it. The conversion is checked against sklearn on
    every training row before it is written; a mismatch fails the run.
    """
    onnx_model = to_onnx(model, features[:1].astype(np.float32), target_opset=ONNX_OPSET)
    payload = onnx_model.SerializeToString()

    session = onnxruntime.InferenceSession(payload, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    onnx_log = session.run(None, {input_name: features.astype(np.float32)})[0].ravel()
    max_diff = float(np.max(np.abs(onnx_log - model.predict(features))))
    if not max_diff < ONNX_TOLERANCE:
        raise SystemExit(f"[train] ONNX export disagrees with sklearn by {max_diff:.3g} "
                         f"(tolerance {ONNX_TOLERANCE}); not publishing")

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_path.write_bytes(payload)
    meta = {
        "model_version": metrics["model_version"],
        "trained_at": metrics["trained_at"],
        "input_name": input_name,
        "output_name": session.get_outputs()[0].name,
        "features": FEATURES,
        "feature_ranges": {name: {"min": round(float(features[:, i].min()), 6),
                                  "max": round(float(features[:, i].max()), 6)}
                           for i, name in enumerate(FEATURES)},
        "target": "log(seconds)",
        "target_inverse": "exp",
        "calibration_scale": 1.0,
        "onnx_vs_sklearn_max_diff": float(f"{max_diff:.3g}"),
        "onnx_bytes": len(payload),
        "n_rows": int(features.shape[0]),
        "holdout_mape_pct": metrics["holdout_mape_pct"],
        "mape_ci_low_pct": metrics["mape_ci_low_pct"],
        "mape_ci_high_pct": metrics["mape_ci_high_pct"],
        "holdout_r2": metrics["holdout_r2"],
        "passes_gate": metrics["passes_gate"],
        "gate_rule": metrics["gate_rule"],
        # The catalogue geometry, so the page derives rows_in and bytes_est the
        # same way workload.py does instead of guessing them.
        "catalogue": {
            "fact_tables": [{"name": name, "rows": rows}
                            for name, rows in FACT_TABLES.items()],
            "fact_row_bytes": FACT_ROW_BYTES,
            "joins": [{"dim": dim, "rows": DIM_ROWS[dim], "row_bytes": DIM_ROW_BYTES[dim]}
                      for dim, _, _ in JOIN_DIMS],
            "selectivities": SELECTIVITIES,
            "limits": LIMITS,
        },
    }
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    print(f"[train] onnx {onnx_path.name} · {len(payload) / 1024:.0f} KB "
          f"· max |onnx - sklearn| {max_diff:.2g}")
    return max_diff


def save_model(model, version: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        pickle.dump({"model": model, "features": FEATURES, "target": "log(seconds)",
                     "model_version": version}, handle)
