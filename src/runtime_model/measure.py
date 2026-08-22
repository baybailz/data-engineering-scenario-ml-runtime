"""Timing queries on DuckDB, well enough that the numbers mean something.

This is the measurement step, and it is the part that is actually hard. A query
that takes 20 ms is mostly scheduler noise, so each query is warmed once and
then repeated until at least 0.6 s of timed work has accumulated (5 repetitions
at minimum, 25 at most), and the median of those repetitions is the reading.

A shared runner also drifts. A noisy neighbour makes everything slower at once,
and a time-ordered holdout reads that as model error. So a fixed calibration
query is re-timed every ten queries and never enters the training set; every
reading is divided by the calibration value interpolated to its position in the
batch. What survives is the part of the runtime that belongs to the query.

DuckDB threads are pinned. An unpinned engine is a different machine on every
run and there is nothing to learn.
"""

import csv
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from .workload import ensure_workload, sql_for

DUCKDB_THREADS = 4
MIN_TIMED_SECONDS = 0.6
MIN_REPS = 5
MAX_REPS = 25

# Re-timed every CALIBRATION_EVERY queries, never trained on.
CALIBRATION_SPEC = {"fact_table": "fact_event_m", "n_joins": 1, "has_groupby": 1,
                    "has_orderby": 0, "has_window": 0, "limit_rows": 0,
                    "selectivity": 0.45}
CALIBRATION_EVERY = 10

MEASUREMENT_COLUMNS = [
    "batch_name", "query_id", "template_id", "template_label", "fact_table",
    "fact_rows", "rows_in", "bytes_est", "n_joins", "has_groupby", "selectivity",
    "has_orderby", "has_window", "limit_rows", "reps", "median_seconds",
    "min_seconds", "max_seconds", "calibration_seconds", "machine_factor",
    "normalized_seconds", "cpu_count", "duckdb_threads", "measured_at",
]


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
    pairs = zip(checkpoints, checkpoints[1:], strict=False)
    for (left, left_seconds), (right, right_seconds) in pairs:
        if left <= index <= right:
            if right == left:
                return left_seconds
            weight = (index - left) / (right - left)
            return left_seconds + (right_seconds - left_seconds) * weight
    return checkpoints[-1][1]


def calibrate(rows: list[dict], checkpoints: list[tuple[int, float]],
              baseline_seconds: float) -> None:
    """Divide every reading by the drift the runner was showing at that moment."""
    for index, row in enumerate(rows):
        calibration = interpolate(checkpoints, index)
        row["calibration_seconds"] = round(calibration, 6)
        row["machine_factor"] = round(calibration / baseline_seconds, 6)
        row["normalized_seconds"] = round(row["median_seconds"] / row["machine_factor"], 6)


def read_batch(path: Path, limit: int | None = None) -> list[dict]:
    with open(path, newline="") as handle:
        queries = list(csv.DictReader(handle))
    return queries[:limit] if limit else queries


def measure_batch(batch_path: Path, baseline_seconds: float | None = None,
                  limit: int | None = None) -> tuple[list[dict], float]:
    """Time every query in one batch file. Returns the rows and the reference reading."""
    facts = machine_facts()
    queries = read_batch(batch_path, limit)
    con = ensure_workload(DUCKDB_THREADS)
    measured_at = datetime.now(UTC).isoformat(timespec="seconds")
    batch_name = batch_path.stem

    calibration_sql = sql_for(CALIBRATION_SPEC)
    checkpoints = [(0, time_query(con, calibration_sql)["median_seconds"])]
    rows = []
    for index, query in enumerate(queries):
        if index and index % CALIBRATION_EVERY == 0:
            checkpoints.append((index, time_query(con, calibration_sql)["median_seconds"]))
        timing = time_query(con, query["query_sql"])
        rows.append({"batch_name": batch_name, "measured_at": measured_at,
                     "cpu_count": facts["cpu_count"], "duckdb_threads": DUCKDB_THREADS,
                     **{c: query[c] for c in MEASUREMENT_COLUMNS if c in query}, **timing})
        print(f"[measure] {index + 1:2d}/{len(queries)} {query['query_id']} "
              f"{timing['median_seconds']:.3f}s ({timing['reps']} reps) "
              f"{query['template_label']}")
    checkpoints.append((len(queries), time_query(con, calibration_sql)["median_seconds"]))
    con.close()

    baseline = baseline_seconds or checkpoints[0][1]
    calibrate(rows, checkpoints, baseline)
    readings = " / ".join(f"{seconds:.3f}" for _, seconds in checkpoints)
    print(f"[calibration] {readings} · reference {baseline:.3f}s")
    return rows, baseline
