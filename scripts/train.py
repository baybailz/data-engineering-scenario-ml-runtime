#!/usr/bin/env python3
"""Train the runtime model on everything measured so far, then publish it.

Runs between the measurement step and dbt. It reads the landing seed of
measured queries, fits two models on log(runtime), scores them on a
time-ordered holdout (the most recent batch), and writes the model, the model
card, the metrics and one prediction row per measured query.

  baseline   ordinary least squares on the same features. The honest floor:
             runtime is close to linear in log(rows), so a straight line is
             already decent and the gradient booster has to beat it.
  model      HistGradientBoostingRegressor, which is what picks up the
             interactions (a sort is cheap under a limit and expensive without
             one; a window over 8M rows is not a window over 100k).

Every published prediction is out of sample. Holdout rows are scored by a model
that never saw the last batch; the earlier rows are scored by 5-fold
cross-validated predictions. The model.pkl that ships is refit on everything,
which is the model you would actually deploy.

The gate is fixed before the numbers are known: holdout MAPE <= 15% and
R2 >= 0.90 on log10 seconds. A failing model is still published and still
labelled on the page.
"""

import csv
import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "seeds"
STATE = ROOT / "state"
ARTIFACTS = ROOT / "artifacts"
RUN_SEED = SEEDS / "query_run_landing.csv"
MODELS_FILE = STATE / "models.json"
PREDICTIONS_FILE = STATE / "predictions.json"

FEATURES = ["log_rows_in", "log_bytes_est", "log_rows_after_filter", "n_joins",
            "has_groupby", "selectivity", "has_orderby", "has_window", "log_limit_rows"]
GATE_MAPE_PCT = 15.0
GATE_R2 = 0.90
GATE_RULE = "holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds"
HOLDOUT_FRACTION = 0.3
BOOTSTRAP_DRAWS = 2000
SEED = 20260821

PREDICTION_COLUMNS = ["model_version", "query_id", "actual_seconds", "predicted_seconds",
                      "abs_pct_error", "in_holdout", "predicted_at"]
MODEL_COLUMNS = ["model_version", "trained_at", "batches_measured", "n_train_rows",
                 "n_holdout_rows", "model_kind", "holdout_mae_seconds", "holdout_mape_pct",
                 "mape_ci_low_pct", "mape_ci_high_pct", "holdout_r2", "cv_mape_pct",
                 "baseline_mape_pct", "passes_gate", "gate_rule"]


def read_runs() -> list[dict]:
    if not RUN_SEED.exists():
        return []
    with open(RUN_SEED, newline="") as handle:
        return list(csv.DictReader(handle))


def featurise(rows: list[dict]) -> np.ndarray:
    matrix = []
    for row in rows:
        fact_rows = float(row["fact_rows"])
        selectivity = float(row["selectivity"])
        matrix.append([
            np.log10(float(row["rows_in"])),
            np.log10(float(row["bytes_est"])),
            np.log10(max(fact_rows * selectivity, 1.0)),
            float(row["n_joins"]),
            float(row["has_groupby"]),
            selectivity,
            float(row["has_orderby"]),
            float(row["has_window"]),
            np.log10(float(row["limit_rows"]) + 1.0),
        ])
    return np.asarray(matrix, dtype=float)


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
    errors = np.abs(predicted - actual) / actual * 100.0
    rng = np.random.default_rng(SEED)
    draws = rng.choice(errors, size=(BOOTSTRAP_DRAWS, errors.size), replace=True).mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


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


def calibration(actual: np.ndarray, predicted: np.ndarray) -> list[dict]:
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


def model_card(metrics: dict, importances: list[dict], calibration_table: list[dict]) -> str:
    lines = [
        f"# Query runtime model {metrics['model_version']}",
        "",
        f"Trained {metrics['trained_at']} on {metrics['n_train_rows']} measured queries "
        f"from {metrics['batches_measured']} batch(es).",
        "",
        "## What it predicts",
        "",
        "Wall-clock seconds for a DuckDB query, from features that are known before the",
        "query runs: rows in the scanned tables, estimated bytes, join count, group by,",
        "filter selectivity, order by, window function, limit.",
        "",
        "## Data",
        "",
        f"- {metrics['n_train_rows'] + metrics['n_holdout_rows']} measured queries, "
        f"median of {metrics['reps_median']} timed repetitions each after a warm-up run.",
        f"- Measured on {metrics['cpu_count']} vCPU, DuckDB threads pinned to "
        f"{metrics['duckdb_threads']}.",
        f"- Runtimes range {metrics['runtime_min_seconds']:.3f}s to "
        f"{metrics['runtime_max_seconds']:.3f}s (median "
        f"{metrics['runtime_median_seconds']:.3f}s).",
        f"- Calibration factors ranged {metrics['machine_factor_min']:.3f} to "
        f"{metrics['machine_factor_max']:.3f}. The calibration query is re-timed every ten "
        f"queries and every reading is divided by the value interpolated to its position.",
        "",
        "## Method",
        "",
        "- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.",
        "- Baseline: ordinary least squares on the same features.",
        "- Holdout: the most recent batch, never used for fitting.",
        "- Published predictions are out of sample (holdout model, or 5-fold "
        "cross-validated for earlier batches).",
        "",
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        f"| holdout MAE | {metrics['holdout_mae_seconds']:.4f} s |",
        f"| holdout MAPE | {metrics['holdout_mape_pct']:.2f}% "
        f"(95% CI {metrics['mape_ci_low_pct']:.2f}–{metrics['mape_ci_high_pct']:.2f}) |",
        f"| holdout R2 (log10 s) | {metrics['holdout_r2']:.4f} |",
        f"| 5-fold CV MAPE | {metrics['cv_mape_pct']:.2f}% |",
        f"| OLS baseline MAPE | {metrics['baseline_mape_pct']:.2f}% |",
        f"| gate | {'PASS' if metrics['passes_gate'] else 'FAIL'} ({GATE_RULE}) |",
        "",
        "## Permutation importance (holdout, log seconds)",
        "",
        "| feature | importance |",
        "|---|---|",
    ]
    lines += [f"| {row['feature']} | {row['importance']:.4f} |" for row in importances]
    lines += ["", "## Calibration", "", "| decile | queries | predicted s | actual s | error |",
              "|---|---|---|---|---|"]
    lines += [f"| {row['decile']} | {row['queries']} | {row['predicted_seconds']:.4f} "
              f"| {row['actual_seconds']:.4f} | {row['abs_pct_error']:.1f}% |"
              for row in calibration_table]
    lines += [
        "",
        "## Limits",
        "",
        "- One engine, one hardware family. A model trained on this runner predicts this",
        "  runner; production would train on production.",
        "- Warm caches. Every query is run once before the timed repetitions.",
        "- The catalogue covers scans, joins to three dimensions, group by, sort, window",
        "  and limit. It does not cover spills to disk, concurrency, or user-defined",
        "  functions, and the model should not be trusted outside that envelope.",
        "",
    ]
    return "\n".join(lines)


def write_seed(name: str, columns: list[str], rows: list[dict]) -> None:
    with open(SEEDS / f"{name}.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = read_runs()
    if len(rows) < 12:
        print(f"[train] {len(rows)} measured queries: not enough to train on yet")
        return

    features = featurise(rows)
    actual = np.array([float(row["normalized_seconds"]) for row in rows])
    actual_log = np.log(actual)
    train_index, holdout_index = split(rows)

    model = new_model().fit(features[train_index], actual_log[train_index])
    baseline = LinearRegression().fit(features[train_index], actual_log[train_index])

    holdout_predicted_log = model.predict(features[holdout_index])
    holdout_predicted = np.exp(holdout_predicted_log)
    holdout_actual = actual[holdout_index]
    baseline_predicted = np.exp(baseline.predict(features[holdout_index]))

    folds = KFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_predicted_log = cross_val_predict(new_model(), features[train_index],
                                         actual_log[train_index], cv=folds)
    cv_predicted = np.exp(cv_predicted_log)

    ci_low, ci_high = bootstrap_mape_ci(holdout_actual, holdout_predicted)
    holdout_mape = mape(holdout_actual, holdout_predicted)
    holdout_r2 = r_squared(np.log10(holdout_actual), np.log10(holdout_predicted))
    passes_gate = bool(holdout_mape <= GATE_MAPE_PCT and holdout_r2 >= GATE_R2)

    digest = hashlib.sha256(
        "|".join(f"{row['query_id']}:{row['median_seconds']}" for row in rows).encode()
    ).hexdigest()[:8]
    history = json.loads(MODELS_FILE.read_text()) if MODELS_FILE.exists() else []
    version = f"v{len(history) + 1}-{digest}"
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batches = sorted({row["batch_name"] for row in rows})

    importance = permutation_importance(model, features[holdout_index],
                                        actual_log[holdout_index], n_repeats=15,
                                        random_state=SEED, scoring="neg_mean_absolute_error")
    importances = sorted(
        [{"feature": name, "importance": round(float(value), 4)}
         for name, value in zip(FEATURES, importance.importances_mean)],
        key=lambda item: item["importance"], reverse=True)

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
        "passes_gate": passes_gate, "gate_rule": GATE_RULE,
        "gate_mape_pct": GATE_MAPE_PCT, "gate_r2": GATE_R2,
        "cpu_count": int(rows[-1]["cpu_count"]), "duckdb_threads": int(rows[-1]["duckdb_threads"]),
        "reps_median": int(np.median(reps)),
        "runtime_min_seconds": float(np.min(actual)),
        "runtime_max_seconds": float(np.max(actual)),
        "runtime_median_seconds": float(np.median(actual)),
        "machine_factor_min": float(min(float(row["machine_factor"]) for row in rows)),
        "machine_factor_max": float(max(float(row["machine_factor"]) for row in rows)),
        "importances": importances,
    }
    metrics["calibration"] = calibration(holdout_actual, holdout_predicted)

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

    history.append({column: metrics[column] for column in MODEL_COLUMNS})
    MODELS_FILE.write_text(json.dumps(history, indent=1) + "\n")
    published = json.loads(PREDICTIONS_FILE.read_text()) if PREDICTIONS_FILE.exists() else {}
    published[version] = prediction_rows
    PREDICTIONS_FILE.write_text(json.dumps(published, indent=1) + "\n")

    write_seed("model_version_landing", MODEL_COLUMNS, history)
    write_seed("query_prediction_landing", PREDICTION_COLUMNS,
               [row for rows_of_version in published.values() for row in rows_of_version])

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    deployed = new_model().fit(features, actual_log)
    with open(ARTIFACTS / "model.pkl", "wb") as handle:
        pickle.dump({"model": deployed, "features": FEATURES, "target": "log(seconds)",
                     "model_version": version}, handle)
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    (ARTIFACTS / "model_card.md").write_text(
        model_card(metrics, importances, metrics["calibration"]))
    with open(ARTIFACTS / "predictions.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(prediction_rows)

    print(f"[train] {version} · {len(train_index)} train / {len(holdout_index)} holdout")
    print(f"[train] holdout MAPE {holdout_mape:.2f}% "
          f"[{ci_low:.2f}, {ci_high:.2f}] · R2 {holdout_r2:.4f} "
          f"· MAE {metrics['holdout_mae_seconds']:.4f}s "
          f"· baseline {metrics['baseline_mape_pct']:.2f}%")
    print(f"[train] gate: {'PASS' if passes_gate else 'FAIL'} ({GATE_RULE})")


if __name__ == "__main__":
    main()
