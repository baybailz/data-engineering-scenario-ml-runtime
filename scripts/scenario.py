"""Scenario hooks for export_json.py.

summary(con, ctx)  -> headline numbers for the page
history(con, ctx)  -> one cell per pipeline step, for the run log
extra(ctx)         -> nothing here; the model card and the metrics ride along
                      in summary so the page needs one fewer fetch
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def metrics() -> dict:
    path = ARTIFACTS / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else {}


def model_card() -> str:
    path = ARTIFACTS / "model_card.md"
    return path.read_text() if path.exists() else ""


def scalar(con, sql: str, default=0):
    value = con.execute(sql).fetchone()
    return default if value is None or value[0] is None else value[0]


def summary(con, ctx) -> dict:
    trained = metrics()
    measured = scalar(con, "select count(*) from main.fact_query_run")
    templates = scalar(con, "select count(*) from main.dim_query_template")
    models = scalar(con, "select count(*) from main.dim_model_version")
    breaches = scalar(
        con, "select count(*) from main.dm_runtime_sla where sla_verdict = 'missed_breach'")
    called = scalar(
        con, "select count(*) from main.dm_runtime_sla where sla_verdict = 'breach_called'")
    slowest = scalar(con, "select max(normalized_seconds) from main.fact_query_run", 0.0)
    fastest = scalar(con, "select min(normalized_seconds) from main.fact_query_run", 0.0)
    return {
        "queries_measured": measured,
        "templates": templates,
        "models_trained": models,
        "model_version": trained.get("model_version"),
        "holdout_mape_pct": trained.get("holdout_mape_pct"),
        "mape_ci_low_pct": trained.get("mape_ci_low_pct"),
        "mape_ci_high_pct": trained.get("mape_ci_high_pct"),
        "holdout_r2": trained.get("holdout_r2"),
        "holdout_mae_seconds": trained.get("holdout_mae_seconds"),
        "baseline_mape_pct": trained.get("baseline_mape_pct"),
        "cv_mape_pct": trained.get("cv_mape_pct"),
        "passes_gate": trained.get("passes_gate"),
        "gate_rule": trained.get("gate_rule"),
        "gate_mape_pct": trained.get("gate_mape_pct"),
        "gate_r2": trained.get("gate_r2"),
        "n_train_rows": trained.get("n_train_rows"),
        "n_holdout_rows": trained.get("n_holdout_rows"),
        "cpu_count": trained.get("cpu_count"),
        "duckdb_threads": trained.get("duckdb_threads"),
        "reps_median": trained.get("reps_median"),
        "importances": trained.get("importances", []),
        "calibration": trained.get("calibration", []),
        "runtime_fastest_seconds": round(float(fastest), 4),
        "runtime_slowest_seconds": round(float(slowest), 4),
        "sla_seconds": scalar(con, "select max(sla_seconds) from main.dm_runtime_sla", 0.0),
        "sla_missed_breaches": breaches,
        "sla_breaches_called": called,
        "model_card": model_card(),
    }


def history(con, ctx) -> dict:
    trained = metrics()
    last_batch = ctx["loaded"][-1] if ctx["action"] != "reset" and ctx["loaded"] else None
    if ctx["action"] == "reset":
        measure = "reset · queue cleared"
        train = "no model"
    elif last_batch:
        counted, median_reps = con.execute(
            "select count(*), median(reps) from main.fact_query_run where batch_name = ?",
            [last_batch]).fetchone()
        measure = (f"{last_batch} · {counted} queries measured "
                   f"({int(median_reps or 0)} reps median)")
        train = "no model"
        if trained:
            train = (f"model {trained['model_version']} · holdout MAPE "
                     f"{trained['holdout_mape_pct']:.1f}% "
                     f"[{trained['mape_ci_low_pct']:.1f}, {trained['mape_ci_high_pct']:.1f}] · "
                     f"R² {trained['holdout_r2']:.2f} · "
                     f"{'PASS' if trained['passes_gate'] else 'FAIL'}")
    else:
        measure = "every batch is already measured"
        train = "no new measurements"
    dbt = (f"dbt build --select {ctx['cfg']['dbt_select']} · PASS={ctx['passed']}"
           if ctx["passed"] else "—")
    return {"measure": measure, "train": train, "dbt": dbt, "batch": last_batch}


def extra(ctx) -> dict:
    return {}
