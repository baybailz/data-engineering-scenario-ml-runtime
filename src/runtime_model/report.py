"""The tables and the model card. Everything a reader is shown, built once.

The page renders numbers; this module is where those numbers are computed, so
there is exactly one definition of "the prediction for query t07_s2" and the
scatter, the table and the SLA verdict cannot disagree with each other.

    prediction_detail   one row per measured query for the published model,
                        with the shape it came from
    sla_table           one row per query shape: does the model call the
                        breach before the query runs
    model_versions      one row per training run, oldest first: the learning
                        curve, and how much was gained over the OLS baseline
    model_card          the markdown card committed beside the pickle
    checks              the assertions the pipeline makes about what it wrote

A missed breach is a page at 3am; a false alarm is a pool sized too big. The
SLA table names both rather than reporting one accuracy number over them.
"""

import pandas as pd

from .train import GATE_RULE

SLA_SECONDS = 0.2

DETAIL_COLUMNS = ["model_version", "query_id", "template_id", "template_label", "batch_name",
                  "n_joins", "has_groupby", "has_orderby", "has_window", "selectivity",
                  "rows_in", "actual_seconds", "predicted_seconds", "error_seconds",
                  "abs_pct_error", "prediction_scope"]
SLA_COLUMNS = ["template_id", "template_label", "queries", "p50_actual_seconds",
               "p50_predicted_seconds", "worst_actual_seconds", "worst_predicted_seconds",
               "mean_abs_pct_error", "sla_verdict", "sla_seconds"]
VERSION_COLUMNS = ["model_sequence", "model_version", "trained_at", "batches_measured",
                   "n_train_rows", "n_holdout_rows", "holdout_mape_pct", "mape_ci_low_pct",
                   "mape_ci_high_pct", "holdout_r2", "holdout_mae_seconds", "cv_mape_pct",
                   "baseline_mape_pct", "mape_gain_over_baseline", "mape_change",
                   "gate_status"]

SHAPE_COLUMNS = ["template_id", "template_label", "batch_name", "n_joins", "has_groupby",
                 "has_orderby", "has_window", "selectivity", "rows_in"]
NUMERIC = ["n_joins", "has_groupby", "has_orderby", "has_window", "selectivity", "rows_in"]


def prediction_detail(measurements: list[dict], predictions: list[dict]) -> list[dict]:
    """The published model's prediction for every measured query, with its shape."""
    if not measurements or not predictions:
        return []
    shapes = {row["query_id"]: row for row in measurements}
    detail = []
    for row in predictions:
        shape = shapes.get(row["query_id"])
        if shape is None:
            continue
        actual = float(row["actual_seconds"])
        predicted = float(row["predicted_seconds"])
        detail.append({
            "model_version": row["model_version"],
            "query_id": row["query_id"],
            **{column: (float(shape[column]) if column in NUMERIC else shape[column])
               for column in SHAPE_COLUMNS},
            "actual_seconds": actual,
            "predicted_seconds": predicted,
            "error_seconds": round(predicted - actual, 6),
            "abs_pct_error": float(row["abs_pct_error"]),
            "prediction_scope": "holdout" if int(row["in_holdout"]) else "cross_validated",
        })
    detail.sort(key=lambda row: row["abs_pct_error"], reverse=True)
    return [{column: row[column] for column in DETAIL_COLUMNS} for row in detail]


def sla_table(detail: list[dict], sla_seconds: float = SLA_SECONDS) -> list[dict]:
    """One row per shape, and whether the model called the breach before the run."""
    if not detail:
        return []
    frame = pd.DataFrame(detail)
    grouped = frame.groupby("template_id", as_index=False).agg(
        template_label=("template_label", "max"),
        queries=("query_id", "count"),
        p50_actual_seconds=("actual_seconds", "median"),
        p50_predicted_seconds=("predicted_seconds", "median"),
        worst_actual_seconds=("actual_seconds", "max"),
        worst_predicted_seconds=("predicted_seconds", "max"),
        mean_abs_pct_error=("abs_pct_error", "mean"),
    )
    actual_breach = grouped["worst_actual_seconds"] > sla_seconds
    predicted_breach = grouped["worst_predicted_seconds"] > sla_seconds
    grouped["sla_verdict"] = [
        "breach_called" if predicted and actual
        else "inside_sla" if not predicted and not actual
        else "missed_breach" if actual
        else "false_alarm"
        for predicted, actual in zip(predicted_breach, actual_breach, strict=True)]
    grouped["sla_seconds"] = sla_seconds
    grouped = grouped.sort_values("worst_actual_seconds", ascending=False)
    rows = grouped[SLA_COLUMNS].to_dict("records")
    for row in rows:
        for column in ("p50_actual_seconds", "p50_predicted_seconds",
                       "worst_actual_seconds", "worst_predicted_seconds"):
            row[column] = round(float(row[column]), 6)
        row["mean_abs_pct_error"] = round(float(row["mean_abs_pct_error"]), 3)
        row["queries"] = int(row["queries"])
    return rows


def model_versions(history: list[dict]) -> list[dict]:
    """The learning curve: one row per training run, oldest first."""
    rows = []
    previous = None
    for sequence, entry in enumerate(history, start=1):
        row = {
            "model_sequence": sequence,
            **{column: entry[column] for column in VERSION_COLUMNS
               if column in entry},
            "mape_gain_over_baseline": round(
                entry["baseline_mape_pct"] - entry["holdout_mape_pct"], 3),
            "mape_change": (None if previous is None
                            else round(entry["holdout_mape_pct"] - previous, 3)),
            "gate_status": "pass" if entry["passes_gate"] else "fail",
        }
        rows.append({column: row.get(column) for column in VERSION_COLUMNS})
        previous = entry["holdout_mape_pct"]
    return rows


def checks(measurements: list[dict], detail: list[dict], versions: list[dict]) -> list[dict]:
    """What the run asserts about what it just wrote. Printed, counted, published.

    These are the assertions that used to be data tests. They run on every
    pipeline run, against the published files, and a failure fails the run.
    """
    measured_ids = {row["query_id"] for row in measurements}
    scored_ids = {row["query_id"] for row in detail}
    negative = [row["query_id"] for row in detail if row["predicted_seconds"] <= 0]
    duplicates = len(detail) - len(scored_ids)
    scopes = {row["prediction_scope"] for row in detail}
    verdicts = {row["gate_status"] for row in versions}
    latest = {row["model_version"] for row in detail}
    return [
        {"check": "every measured query has a prediction", "ok": scored_ids == measured_ids,
         "detail": f"{len(scored_ids)} of {len(measured_ids)} measured queries scored"},
        {"check": "no prediction is zero or negative", "ok": not negative,
         "detail": f"{len(negative)} non-positive predictions"},
        {"check": "one prediction per query", "ok": duplicates == 0,
         "detail": f"{duplicates} duplicate query_id rows"},
        {"check": "every prediction is out of sample",
         "ok": scopes <= {"holdout", "cross_validated"},
         "detail": f"scopes {sorted(scopes) or ['none']}"},
        {"check": "one published model at a time", "ok": len(latest) <= 1,
         "detail": f"{len(latest)} model version(s) in the detail table"},
        {"check": "every model version is gated",
         "ok": verdicts <= {"pass", "fail"} and len(versions) > 0,
         "detail": f"{len(versions)} version(s), verdicts {sorted(verdicts) or ['none']}"},
    ]


def model_card(metrics: dict) -> str:
    """The card that ships with the pickle. Results, limits, and how it was measured."""
    importances = metrics.get("importances", [])
    calibration = metrics.get("calibration", [])
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
        f"(95% CI {metrics['mape_ci_low_pct']:.2f}-{metrics['mape_ci_high_pct']:.2f}) |",
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
              for row in calibration]
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
