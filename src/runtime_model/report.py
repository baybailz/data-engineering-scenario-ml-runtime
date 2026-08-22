"""The tables and the model card. Everything a reader is shown, built once.

The page renders numbers; this module is where those numbers are computed, so
there is exactly one definition of "the prediction for this QUERY_ID" and the
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

SLA_MS = 200.0

DETAIL_COLUMNS = ["model_version", "query_id", "template_id", "template_label", "batch_name",
                  "warehouse_size", "n_tables", "n_joins", "has_group_by", "has_order_by",
                  "has_window", "predicate_literal", "table_rows", "actual_ms",
                  "predicted_ms", "error_ms", "abs_pct_error", "prediction_scope"]
SLA_COLUMNS = ["template_id", "template_label", "queries", "p50_actual_ms",
               "p50_predicted_ms", "worst_actual_ms", "worst_predicted_ms",
               "mean_abs_pct_error", "sla_verdict", "sla_ms"]
VERSION_COLUMNS = ["model_sequence", "model_version", "trained_at", "batches_measured",
                   "n_train_rows", "n_holdout_rows", "holdout_mape_pct", "mape_ci_low_pct",
                   "mape_ci_high_pct", "holdout_r2", "holdout_mae_ms", "cv_mape_pct",
                   "baseline_mape_pct", "mape_gain_over_baseline", "mape_change",
                   "gate_status"]

SHAPE_COLUMNS = ["template_id", "template_label", "batch_name", "warehouse_size", "n_tables",
                 "n_joins", "has_group_by", "has_order_by", "has_window", "predicate_literal",
                 "table_rows"]
NUMERIC = ["n_tables", "n_joins", "has_group_by", "has_order_by", "has_window",
           "predicate_literal", "table_rows"]


def prediction_detail(measurements: list[dict], predictions: list[dict],
                      tables: dict | None = None) -> list[dict]:
    """The published model's prediction for every measured query, with its shape.

    The shape columns are parsed back out of QUERY_TEXT rather than carried
    along beside it, so what the table shows is what the model saw.
    """
    if not measurements or not predictions:
        return []
    shapes = {row["QUERY_ID"]: describe(row, tables or {}) for row in measurements}
    detail = []
    for row in predictions:
        shape = shapes.get(row["query_id"])
        if shape is None:
            continue
        actual = float(row["actual_ms"])
        predicted = float(row["predicted_ms"])
        detail.append({
            "model_version": row["model_version"],
            "query_id": row["query_id"],
            **{column: (float(shape[column]) if column in NUMERIC else shape[column])
               for column in SHAPE_COLUMNS},
            "actual_ms": actual,
            "predicted_ms": predicted,
            "error_ms": round(predicted - actual, 3),
            "abs_pct_error": float(row["abs_pct_error"]),
            "prediction_scope": "holdout" if int(row["in_holdout"]) else "cross_validated",
        })
    detail.sort(key=lambda row: row["abs_pct_error"], reverse=True)
    return [{column: row[column] for column in DETAIL_COLUMNS} for row in detail]


def describe(row: dict, tables: dict) -> dict:
    """One QUERY_HISTORY row as the shape columns the page displays."""
    from .parse import shape as parse_shape

    parsed = parse_shape(row["QUERY_TEXT"], row["WAREHOUSE_SIZE"], tables)
    return {"template_id": row.get("TEMPLATE_ID"), "template_label": row.get("TEMPLATE_LABEL"),
            "batch_name": row.get("QUERY_TAG"), "warehouse_size": row["WAREHOUSE_SIZE"],
            **{key: parsed[key] for key in
               ("n_tables", "n_joins", "has_group_by", "has_order_by", "has_window",
                "predicate_literal", "table_rows")}}


def sla_table(detail: list[dict], sla_ms: float = SLA_MS) -> list[dict]:
    """One row per shape, and whether the model called the breach before the run."""
    if not detail:
        return []
    frame = pd.DataFrame(detail)
    grouped = frame.groupby("template_id", as_index=False).agg(
        template_label=("template_label", "max"),
        queries=("query_id", "count"),
        p50_actual_ms=("actual_ms", "median"),
        p50_predicted_ms=("predicted_ms", "median"),
        worst_actual_ms=("actual_ms", "max"),
        worst_predicted_ms=("predicted_ms", "max"),
        mean_abs_pct_error=("abs_pct_error", "mean"),
    )
    actual_breach = grouped["worst_actual_ms"] > sla_ms
    predicted_breach = grouped["worst_predicted_ms"] > sla_ms
    grouped["sla_verdict"] = [
        "breach_called" if predicted and actual
        else "inside_sla" if not predicted and not actual
        else "missed_breach" if actual
        else "false_alarm"
        for predicted, actual in zip(predicted_breach, actual_breach, strict=True)]
    grouped["sla_ms"] = sla_ms
    grouped = grouped.sort_values("worst_actual_ms", ascending=False)
    rows = grouped[SLA_COLUMNS].to_dict("records")
    for row in rows:
        for column in ("p50_actual_ms", "p50_predicted_ms",
                       "worst_actual_ms", "worst_predicted_ms"):
            row[column] = round(float(row[column]), 3)
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
    measured_ids = {row["QUERY_ID"] for row in measurements}
    scored_ids = {row["query_id"] for row in detail}
    negative = [row["query_id"] for row in detail if row["predicted_ms"] <= 0]
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
        "EXECUTION_TIME in milliseconds, from the QUERY_HISTORY columns that exist at",
        "submit time: the parsed QUERY_TEXT, WAREHOUSE_SIZE, the ROW_COUNT and BYTES of",
        "the tables it names, and what the same QUERY_PARAMETERIZED_HASH cost before.",
        "",
        "## Data",
        "",
        f"- {metrics['n_train_rows'] + metrics['n_holdout_rows']} measured queries, "
        f"median of {metrics['reps_median']} timed repetitions each after a warm-up run.",
        f"- Engine {metrics['engine']}, warehouse sizes "
        f"{', '.join(metrics['warehouse_sizes'])} applied as thread counts.",
        f"- Runtimes range {metrics['runtime_min_ms']:.1f} ms to "
        f"{metrics['runtime_max_ms']:.1f} ms (median "
        f"{metrics['runtime_median_ms']:.1f} ms).",
        f"- Calibration factors ranged {metrics['machine_factor_min']:.3f} to "
        f"{metrics['machine_factor_max']:.3f}. The calibration query is re-timed every ten "
        f"queries and every reading is divided by the value interpolated to its position.",
        "",
        "## Method",
        "",
        "- Target: log(EXECUTION_TIME in ms, runner drift divided out). Model: "
        "HistGradientBoostingRegressor.",
        "- Baseline: ordinary least squares on the same features.",
        "- Holdout: the most recent batch, never used for fitting.",
        "- Published predictions are out of sample (holdout model, or 5-fold "
        "cross-validated for earlier batches).",
        "",
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        f"| holdout MAE | {metrics['holdout_mae_ms']:.2f} ms |",
        f"| holdout MAPE | {metrics['holdout_mape_pct']:.2f}% "
        f"(95% CI {metrics['mape_ci_low_pct']:.2f}-{metrics['mape_ci_high_pct']:.2f}) |",
        f"| holdout R2 (log10 ms) | {metrics['holdout_r2']:.4f} |",
        f"| 5-fold CV MAPE | {metrics['cv_mape_pct']:.2f}% |",
        f"| OLS baseline MAPE | {metrics['baseline_mape_pct']:.2f}% |",
        f"| gate | {'PASS' if metrics['passes_gate'] else 'FAIL'} ({GATE_RULE}) |",
        "",
        "## Permutation importance (holdout, log ms)",
        "",
        "| feature | importance |",
        "|---|---|",
    ]
    lines += [f"| {row['feature']} | {row['importance']:.4f} |" for row in importances]
    lines += ["", "## Calibration", "",
              "| decile | queries | predicted ms | actual ms | error |", "|---|---|---|---|---|"]
    lines += [f"| {row['decile']} | {row['queries']} | {row['predicted_ms']:.1f} "
              f"| {row['actual_ms']:.1f} | {row['abs_pct_error']:.1f}% |"
              for row in calibration]
    lines += [
        "",
        "## Limits",
        "",
        "- One engine, one hardware family. A model trained on this runner predicts this",
        "  runner; production would train on production.",
        "- Warm caches. Every query is run once before the timed repetitions.",
        "- The catalogue covers scans, joins to three dimensions, group by, sort, window",
        "  and limit, on three warehouse sizes. It does not cover spills to disk,",
        "  concurrency, or user-defined functions, and the model should not be trusted",
        "  outside that envelope.",
        "",
    ]
    return "\n".join(lines)
