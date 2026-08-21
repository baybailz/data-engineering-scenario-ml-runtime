#!/usr/bin/env python3
"""The measurement step: run the next batch of queries and record what they cost.

This is the ingest stage of the scenario, except the data does not arrive in a
file: it is produced on the runner. Each query in the batch is executed once to
warm the caches, then repeated until at least 0.6 s of timed work has
accumulated (at least 5 repetitions, at most 25), and the median wall time of
those repetitions is the reading. Sub-100 ms queries need the repetitions:
below that, scheduler noise is bigger than the effect being measured.

A fixed calibration query is re-measured every ten queries. The label is the
reading divided by the calibration value interpolated to that query's position,
so a runner that got busy halfway through a batch is not read as a batch that
turned slower halfway through.

The features are all recorded from the catalogue, never from the run: table
sizes, join count, group by, filter selectivity, order by, window, limit. That
is the whole point. A feature that is only knowable afterwards would make the
model useless for the thing it is for.

    --action measure_batch   measure the next batch in the queue (default)
    --action reset           clear the queue, the measurements and the model

The landing seeds are rebuilt from state/ on every run, so they are a pure
function of the state files and a re-run cannot double-count anything.
"""

import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from make_workload import ensure_workload, sql_for

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
STATE = ROOT / "state"
SEEDS = ROOT / "seeds"
ARTIFACTS = ROOT / "artifacts"
DOCS_DATA = ROOT / "docs" / "data"
STATE_FILE = STATE / "loaded_files.json"
MEASUREMENTS_FILE = STATE / "measurements.json"
MACHINE_FILE = STATE / "machine.json"
MODELS_FILE = STATE / "models.json"
PREDICTIONS_FILE = STATE / "predictions.json"

DUCKDB_THREADS = 4
MIN_TIMED_SECONDS = 0.6
MIN_REPS = 5
MAX_REPS = 25

# The calibration query. It is re-measured every CALIBRATION_EVERY queries and
# never enters the training set. A shared runner drifts: a noisy neighbour makes
# every query slower at once, and a time-ordered holdout turns that drift into
# apparent model error. Each reading is divided by the calibration value
# interpolated to its position in the batch, which removes the part of the drift
# that is common to everything running at that moment.
CALIBRATION_SPEC = {"fact_table": "fact_event_m", "n_joins": 1, "has_groupby": 1,
                    "has_orderby": 0, "has_window": 0, "limit_rows": 0,
                    "selectivity": 0.45}
CALIBRATION_EVERY = 10

RUN_COLUMNS = [
    "batch_name", "query_id", "template_id", "template_label", "fact_table",
    "fact_rows", "rows_in", "bytes_est", "n_joins", "has_groupby", "selectivity",
    "has_orderby", "has_window", "limit_rows", "reps", "median_seconds",
    "min_seconds", "max_seconds", "calibration_seconds", "machine_factor",
    "normalized_seconds", "cpu_count", "duckdb_threads", "measured_at",
]
PREDICTION_COLUMNS = [
    "model_version", "query_id", "actual_seconds", "predicted_seconds",
    "abs_pct_error", "in_holdout", "predicted_at",
]
MODEL_COLUMNS = [
    "model_version", "trained_at", "batches_measured", "n_train_rows", "n_holdout_rows",
    "model_kind", "holdout_mae_seconds", "holdout_mape_pct", "mape_ci_low_pct",
    "mape_ci_high_pct", "holdout_r2", "cv_mape_pct", "baseline_mape_pct",
    "passes_gate", "gate_rule",
]


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")


def write_seed(name: str, columns: list[str], rows: list[dict]) -> int:
    with open(SEEDS / f"{name}.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def machine_facts() -> dict:
    return {"cpu_count": os.cpu_count(), "duckdb_threads": DUCKDB_THREADS,
            "platform": platform.platform(), "python": platform.python_version()}


def time_query(con, sql: str) -> dict:
    """Warm once, then repeat until the timed work is long enough to trust."""
    con.execute(f"create or replace temp table q_result as {sql}")
    timings, spent = [], 0.0
    while len(timings) < MIN_REPS or (spent < MIN_TIMED_SECONDS and len(timings) < MAX_REPS):
        started = time.perf_counter()
        con.execute(f"create or replace temp table q_result as {sql}")
        elapsed = time.perf_counter() - started
        timings.append(elapsed)
        spent += elapsed
    return {"reps": len(timings), "median_seconds": round(statistics.median(timings), 6),
            "min_seconds": round(min(timings), 6), "max_seconds": round(max(timings), 6)}


def interpolate(checkpoints: list[tuple[int, float]], index: int) -> float:
    """The calibration value at one position, straight-lined between readings."""
    for (left, left_seconds), (right, right_seconds) in zip(checkpoints, checkpoints[1:]):
        if left <= index <= right:
            if right == left:
                return left_seconds
            weight = (index - left) / (right - left)
            return left_seconds + (right_seconds - left_seconds) * weight
    return checkpoints[-1][1]


def measure_batch(batch_name: str, baseline_seconds: float | None,
                  limit: int | None = None) -> tuple[list[dict], float]:
    facts = machine_facts()
    with open(INCOMING / f"{batch_name}.csv", newline="") as handle:
        queries = list(csv.DictReader(handle))
    if limit:
        queries = queries[:limit]
    con = ensure_workload(DUCKDB_THREADS)
    measured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    calibration_sql = sql_for(CALIBRATION_SPEC)
    checkpoints = [(0, time_query(con, calibration_sql)["median_seconds"])]
    rows = []
    for index, query in enumerate(queries):
        if index and index % CALIBRATION_EVERY == 0:
            checkpoints.append((index, time_query(con, calibration_sql)["median_seconds"]))
        timing = time_query(con, query["query_sql"])
        rows.append({"batch_name": batch_name, "measured_at": measured_at,
                     "cpu_count": facts["cpu_count"], "duckdb_threads": DUCKDB_THREADS,
                     **{c: query[c] for c in RUN_COLUMNS if c in query}, **timing})
        print(f"[measure] {index + 1:2d}/{len(queries)} {query['query_id']} "
              f"{timing['median_seconds']:.3f}s ({timing['reps']} reps) {query['template_label']}")
    checkpoints.append((len(queries), time_query(con, calibration_sql)["median_seconds"]))
    con.close()

    baseline = baseline_seconds or checkpoints[0][1]
    for index, row in enumerate(rows):
        calibration = interpolate(checkpoints, index)
        row["calibration_seconds"] = round(calibration, 6)
        row["machine_factor"] = round(calibration / baseline, 6)
        row["normalized_seconds"] = round(row["median_seconds"] / row["machine_factor"], 6)
    readings = " / ".join(f"{seconds:.3f}" for _, seconds in checkpoints)
    print(f"[calibration] {readings} · reference {baseline:.3f}s")
    return rows, baseline


def rebuild_run_seed(loaded: list[str], measurements: dict) -> int:
    rows = [row for name in loaded for row in measurements.get(name, [])]
    return write_seed("query_run_landing", RUN_COLUMNS, rows)


def reset() -> None:
    for path in (STATE_FILE, MEASUREMENTS_FILE, MODELS_FILE, PREDICTIONS_FILE, MACHINE_FILE):
        path.unlink(missing_ok=True)
    write_json(STATE_FILE, [])
    write_seed("query_run_landing", RUN_COLUMNS, [])
    write_seed("query_prediction_landing", PREDICTION_COLUMNS, [])
    write_seed("model_version_landing", MODEL_COLUMNS, [])
    for path in (DOCS_DATA / "model.onnx", DOCS_DATA / "model_meta.json"):
        path.unlink(missing_ok=True)
    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / ".gitkeep").write_text("")
    print("[reset] queue, measurements and trained model cleared")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="measure_batch", choices=["measure_batch", "reset"])
    parser.add_argument("--limit", type=int, default=0,
                        help="measure only the first N queries of the batch (CI smoke test)")
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)

    if args.action == "reset":
        reset()
        return

    loaded = read_json(STATE_FILE, [])
    measurements = read_json(MEASUREMENTS_FILE, {})
    pending = [p.stem for p in sorted(INCOMING.glob("batch_*.csv")) if p.stem not in loaded]
    if not pending:
        print("[measure] every batch has been measured")
    else:
        batch_name = pending[0]
        facts = machine_facts()
        print(f"[machine] {facts['cpu_count']} cpu · duckdb threads={DUCKDB_THREADS} "
              f"· {facts['platform']}")
        print(f"[pickup] {batch_name}.csv")
        machine = read_json(MACHINE_FILE, {})
        rows, baseline = measure_batch(batch_name, machine.get("calibration_baseline_seconds"),
                                       args.limit or None)
        measurements[batch_name] = rows
        loaded.append(batch_name)
        write_json(MACHINE_FILE, {**facts, "calibration_baseline_seconds": baseline})
        write_json(MEASUREMENTS_FILE, measurements)
        write_json(STATE_FILE, loaded)

    total = rebuild_run_seed(loaded, measurements)
    print(f"[seed] query_run_landing → {total} measured queries from {len(loaded)} batch(es)")


if __name__ == "__main__":
    main()
