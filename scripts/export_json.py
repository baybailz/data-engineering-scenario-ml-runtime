#!/usr/bin/env python3
"""Publish docs/data/*.json: everything the page reads, and nothing it invents.

    summary.json     queue state, row counts, the headline numbers
    tables.json      the published tables: predictions, model versions, SLA
    next_file.json   the queue -- the next batch, scored before it is measured
    logs.json        run history (one entry per run) plus the raw run log
    models.json      the project source, for the code browser
    model_data.json  the rows behind each published table, for the play button

Input is data/*.csv and artifacts/, written by scripts/run.py. The model itself
(docs/data/model.onnx and model_meta.json) is written by the training step, not
here. There is no warehouse and no query engine in this file: it reads the CSVs
the solution published and turns them into JSON.

    python scripts/export_json.py --action measure_batch --log /tmp/run.log
"""

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runtime_model import predict, report  # noqa: E402

OUT = ROOT / "docs" / "data"
DATA = ROOT / "data"
STATE = ROOT / "state"
ARTIFACTS = ROOT / "artifacts"
INCOMING = ROOT / "incoming"
CFG = json.loads((ROOT / "docs" / "scenario.json").read_text())
HISTORY_LIMIT = 12
SAMPLE_ROWS = 120

# src/ first, so the code browser opens on the package overview.
SOURCE_GLOBS = ["src/runtime_model/*.py", "scripts/*.py", "tests/*.py",
                ".github/workflows/*.yml", "data/*.csv"]


def coerce(value: str):
    """CSV is all strings. The page does arithmetic, so give it numbers."""
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def read_csv(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit:
        rows = rows[:limit]
    return [{key: coerce(value) for key, value in row.items()} for row in rows]


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def read_log(path: str | None) -> str:
    file = Path(path) if path else None
    return file.read_text(errors="replace").rstrip() if file and file.exists() else ""


def forecast(rows: list[dict]) -> list[dict]:
    """Score the queued queries with the published model, before they are run.

    This is the product, shown where it is most obvious: the incoming batch
    arrives with a predicted runtime already attached, and the next run
    measures the same queries so the claim can be checked.
    """
    model_file = ARTIFACTS / "model.pkl"
    if not rows or not model_file.exists():
        return rows
    bundle = predict.load_model(model_file)
    seconds = predict.predict_rows(bundle["model"], rows)
    for row, value in zip(rows, seconds, strict=True):
        row["predicted_seconds"] = round(value, 4)
        row["predicted_by"] = bundle["model_version"]
    return rows


def counts(rows: list[dict], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def build_summary(now: str, loaded: list[str], queue: list[str], tables: dict,
                  metrics: dict, checks: list[dict]) -> dict:
    measurements = tables["measurements"]
    sla = tables["sla"]
    runtimes = [row["normalized_seconds"] for row in measurements]
    return {
        "generated_at": now,
        "files_loaded": loaded,
        "files_pending": queue,
        "next_file": queue[0] if queue else None,
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "queries_measured": len(measurements),
        "templates": len({row["template_id"] for row in measurements}),
        "models_trained": len(tables["model_versions"]),
        "model_version": metrics.get("model_version"),
        "holdout_mape_pct": metrics.get("holdout_mape_pct"),
        "mape_ci_low_pct": metrics.get("mape_ci_low_pct"),
        "mape_ci_high_pct": metrics.get("mape_ci_high_pct"),
        "holdout_r2": metrics.get("holdout_r2"),
        "holdout_mae_seconds": metrics.get("holdout_mae_seconds"),
        "baseline_mape_pct": metrics.get("baseline_mape_pct"),
        "cv_mape_pct": metrics.get("cv_mape_pct"),
        "passes_gate": metrics.get("passes_gate"),
        "gate_rule": metrics.get("gate_rule"),
        "gate_mape_pct": metrics.get("gate_mape_pct"),
        "gate_r2": metrics.get("gate_r2"),
        "n_train_rows": metrics.get("n_train_rows"),
        "n_holdout_rows": metrics.get("n_holdout_rows"),
        "cpu_count": metrics.get("cpu_count"),
        "duckdb_threads": metrics.get("duckdb_threads"),
        "reps_median": metrics.get("reps_median"),
        "importances": metrics.get("importances", []),
        "calibration": metrics.get("calibration", []),
        "runtime_fastest_seconds": round(min(runtimes), 4) if runtimes else 0.0,
        "runtime_slowest_seconds": round(max(runtimes), 4) if runtimes else 0.0,
        "sla_seconds": sla[0]["sla_seconds"] if sla else report.SLA_SECONDS,
        "sla_breaches_called": counts(sla, "sla_verdict", "breach_called"),
        "sla_missed_breaches": counts(sla, "sla_verdict", "missed_breach"),
        "checks_passed": sum(1 for check in checks if check["ok"]),
        "checks_failed": sum(1 for check in checks if not check["ok"]),
        "checks": checks,
        "model_card": (ARTIFACTS / "model_card.md").read_text()
        if (ARTIFACTS / "model_card.md").exists() else "",
    }


def build_history_entry(now: str, action: str, loaded: list[str], tables: dict,
                        metrics: dict, checks: list[dict]) -> dict:
    """One row of the run log: what each step of this run did."""
    batch = loaded[-1] if action != "reset" and loaded else None
    if action == "reset":
        return {"at": now, "action": action, "passed": 0, "failed": 0, "batch": None,
                "measure": "reset · queue cleared", "train": "no model",
                "publish": "published tables emptied"}
    measured = [row for row in tables["measurements"] if row["batch_name"] == batch]
    if batch and measured:
        reps = sorted(row["reps"] for row in measured)
        measure = (f"{batch} · {len(measured)} queries measured "
                   f"({reps[len(reps) // 2]} reps median)")
    else:
        measure = "every batch is already measured"
    train = "no model"
    if metrics:
        train = (f"model {metrics['model_version']} · holdout MAPE "
                 f"{metrics['holdout_mape_pct']:.1f}% "
                 f"[{metrics['mape_ci_low_pct']:.1f}, {metrics['mape_ci_high_pct']:.1f}] · "
                 f"R² {metrics['holdout_r2']:.2f} · "
                 f"{'PASS' if metrics['passes_gate'] else 'FAIL'}")
    passed = sum(1 for check in checks if check["ok"])
    failed = sum(1 for check in checks if not check["ok"])
    publish = (f"{len(tables['predictions'])} predictions · checks PASS={passed}"
               if checks else "nothing to publish yet")
    return {"at": now, "action": action, "passed": passed, "failed": failed,
            "batch": batch, "measure": measure, "train": train, "publish": publish}


def build_models() -> dict:
    """The project source, published from the repo so the deck cannot drift."""
    files = []
    for pattern in SOURCE_GLOBS:
        files += sorted(path for path in ROOT.glob(pattern) if path.is_file())
    return {"files": [{"path": path.relative_to(ROOT).as_posix(), "sql": path.read_text()}
                      for path in files],
            # No templating anywhere: the source is the thing that runs.
            "compiled": {}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", help="the run log, published under the console")
    parser.add_argument("--action", default="measure_batch")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    loaded = read_json(STATE / "loaded_files.json", [])
    queue = [path.stem for path in sorted(INCOMING.glob("*.csv")) if path.stem not in loaded]
    tables = {name: read_csv(DATA / f"{name}.csv")
              for name in ("measurements", "predictions", "model_versions", "sla")}
    metrics = read_json(ARTIFACTS / "metrics.json", {})

    check_results = report.checks(tables["measurements"], tables["predictions"],
                                  tables["model_versions"]) if tables["predictions"] else []
    summary = build_summary(now, loaded, queue, tables, metrics, check_results)
    entry = build_history_entry(now, args.action, loaded, tables, metrics, check_results)

    previous = []
    if args.action != "reset" and (OUT / "logs.json").exists():
        try:
            previous = json.loads((OUT / "logs.json").read_text()).get("history", [])
        except (ValueError, OSError):
            previous = []
    logs = {"generated_at": now, "action": args.action,
            "passed": entry["passed"], "failed": entry["failed"],
            "history": (previous + [entry])[-HISTORY_LIMIT:],
            "python": read_log(args.log)}

    next_name = queue[0] if queue else None
    next_rows = forecast(read_csv(INCOMING / f"{next_name}.csv")) if next_name else []

    published = {name: tables[name] for name in CFG["export"]["tables"]}
    for name, payload in [
        ("summary.json", summary),
        ("tables.json", published),
        ("next_file.json", {"name": next_name, "rows": next_rows}),
        ("logs.json", logs),
        ("models.json", build_models()),
        ("model_data.json", {name: read_csv(DATA / f"{name}.csv", SAMPLE_ROWS)
                             for name in tables}),
    ]:
        (OUT / name).write_text(json.dumps(payload, indent=1, default=str) + "\n")
        print(f"wrote docs/data/{name}")


if __name__ == "__main__":
    main()
