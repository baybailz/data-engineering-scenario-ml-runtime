#!/usr/bin/env python3
"""One batch, end to end: measure, train, predict, publish.

    python scripts/run.py --action measure_batch   the next batch in the queue
    python scripts/run.py --action reset           back to the starting state
    python scripts/run.py --action measure_batch --limit 16    a short batch

Nothing arrives in a file. The data is produced here, by timing real queries on
this machine, and state/ is the record of what has been measured so far. Every
published file is rebuilt from state/ on every run, so a re-run is idempotent
and cannot double-count a batch.

The publish step ends with a set of checks against the files it just wrote. If
one fails the run fails and nothing is committed.
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runtime_model import report, train  # noqa: E402
from runtime_model.measure import MEASUREMENT_COLUMNS, machine_facts, measure_batch  # noqa: E402

INCOMING = ROOT / "incoming"
STATE = ROOT / "state"
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
DOCS_DATA = ROOT / "docs" / "data"

LOADED_FILE = STATE / "loaded_files.json"
MEASUREMENTS_FILE = STATE / "measurements.json"
MACHINE_FILE = STATE / "machine.json"
MODELS_FILE = STATE / "models.json"
PREDICTIONS_FILE = STATE / "predictions.json"

PUBLISHED = {
    "measurements.csv": MEASUREMENT_COLUMNS,
    "predictions.csv": report.DETAIL_COLUMNS,
    "model_versions.csv": report.VERSION_COLUMNS,
    "sla.csv": report.SLA_COLUMNS,
}


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")


def write_csv(name: str, columns: list[str], rows: list[dict]) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / name, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def measured_rows(loaded: list[str], measurements: dict) -> list[dict]:
    """Every measurement so far, in the order the batches were measured."""
    return [row for name in loaded for row in measurements.get(name, [])]


def publish(rows: list[dict], history: list[dict], predictions: dict) -> list[dict]:
    """Rebuild every published table from state, then check what was written."""
    latest = history[-1]["model_version"] if history else None
    detail = report.prediction_detail(rows, predictions.get(latest, []) if latest else [])
    versions = report.model_versions(history)
    sla = report.sla_table(detail)

    counts = {
        "measurements.csv": write_csv("measurements.csv", MEASUREMENT_COLUMNS, rows),
        "predictions.csv": write_csv("predictions.csv", report.DETAIL_COLUMNS, detail),
        "model_versions.csv": write_csv("model_versions.csv", report.VERSION_COLUMNS, versions),
        "sla.csv": write_csv("sla.csv", report.SLA_COLUMNS, sla),
    }
    for name, count in counts.items():
        print(f"[publish] data/{name} → {count} rows")

    if not detail:
        return []
    results = report.checks(rows, detail, versions)
    for result in results:
        print(f"[check] {'PASS' if result['ok'] else 'FAIL'} · {result['check']} "
              f"· {result['detail']}")
    failed = [result["check"] for result in results if not result["ok"]]
    if failed:
        raise SystemExit(f"[check] {len(failed)} check(s) failed: {', '.join(failed)}")
    return results


def train_on(rows: list[dict]) -> tuple[list[dict], dict]:
    """Fit on everything measured so far and write the model, the card and the ONNX."""
    history = read_json(MODELS_FILE, [])
    predictions = read_json(PREDICTIONS_FILE, {})
    if len(rows) < train.MIN_ROWS_TO_TRAIN:
        print(f"[train] {len(rows)} measured queries: not enough to train on yet")
        return history, predictions

    result = train.fit(rows, history)
    metrics, version = result["metrics"], result["metrics"]["model_version"]
    history.append({column: metrics[column] for column in train.MODEL_COLUMNS})
    predictions[version] = result["predictions"]
    write_json(MODELS_FILE, history)
    write_json(PREDICTIONS_FILE, predictions)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    train.save_model(result["model"], version, ARTIFACTS / "model.pkl")
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    (ARTIFACTS / "model_card.md").write_text(report.model_card(metrics))
    train.export_onnx(result["model"], result["features"], metrics,
                      DOCS_DATA / "model.onnx", DOCS_DATA / "model_meta.json")

    print(f"[train] {version} · {metrics['n_train_rows']} train / "
          f"{metrics['n_holdout_rows']} holdout")
    print(f"[train] holdout MAPE {metrics['holdout_mape_pct']:.2f}% "
          f"[{metrics['mape_ci_low_pct']:.2f}, {metrics['mape_ci_high_pct']:.2f}] "
          f"· R2 {metrics['holdout_r2']:.4f} · MAE {metrics['holdout_mae_seconds']:.4f}s "
          f"· baseline {metrics['baseline_mape_pct']:.2f}%")
    print(f"[train] gate: {'PASS' if metrics['passes_gate'] else 'FAIL'} "
          f"({train.GATE_RULE})")
    return history, predictions


def reset() -> None:
    for path in (LOADED_FILE, MEASUREMENTS_FILE, MODELS_FILE, PREDICTIONS_FILE, MACHINE_FILE):
        path.unlink(missing_ok=True)
    write_json(LOADED_FILE, [])
    for name, columns in PUBLISHED.items():
        write_csv(name, columns, [])
    for path in (DOCS_DATA / "model.onnx", DOCS_DATA / "model_meta.json"):
        path.unlink(missing_ok=True)
    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / ".gitkeep").write_text("")
    print("[reset] queue, measurements and trained model cleared")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="measure_batch",
                        choices=["measure_batch", "reset"])
    parser.add_argument("--limit", type=int, default=0,
                        help="measure only the first N queries of the batch (CI smoke test)")
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)

    if args.action == "reset":
        reset()
        return

    loaded = read_json(LOADED_FILE, [])
    measurements = read_json(MEASUREMENTS_FILE, {})
    pending = [p.stem for p in sorted(INCOMING.glob("batch_*.csv")) if p.stem not in loaded]

    if not pending:
        print("[measure] every batch has been measured")
    else:
        batch_name = pending[0]
        facts = machine_facts()
        print(f"[machine] {facts['cpu_count']} cpu · duckdb threads="
              f"{facts['duckdb_threads']} · {facts['platform']}")
        print(f"[pickup] {batch_name}.csv")
        machine = read_json(MACHINE_FILE, {})
        rows, baseline = measure_batch(INCOMING / f"{batch_name}.csv",
                                       machine.get("calibration_baseline_seconds"),
                                       args.limit or None)
        measurements[batch_name] = rows
        loaded.append(batch_name)
        write_json(MACHINE_FILE, {**facts, "calibration_baseline_seconds": baseline})
        write_json(MEASUREMENTS_FILE, measurements)
        write_json(LOADED_FILE, loaded)

    rows = measured_rows(loaded, measurements)
    print(f"[measure] {len(rows)} measured queries from {len(loaded)} batch(es)")
    history, predictions = train_on(rows)
    publish(rows, history, predictions)


if __name__ == "__main__":
    main()
