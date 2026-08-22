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

WAREHOUSE_SIZE is applied, not decorated: X-Small, Small and Medium are set on
the engine as one, two and four threads before the query is timed. The size in
the published row is the size that ran.

Every reading leaves here as a QUERY_HISTORY row -- real SQL text, real start
and end times, measured EXECUTION_TIME and COMPILATION_TIME, exact
ROWS_PRODUCED, and NULL everywhere a local engine has nothing to report. The
drift factor has no Snowflake column, so it is published separately in
data/calibration.csv rather than smuggled into one.
"""

import csv
import os
import platform
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from . import snowflake
from .workload import ensure_workload, sql_for

DUCKDB_THREADS = 4
MIN_TIMED_SECONDS = 0.6
MIN_REPS = 5
MAX_REPS = 25

# Re-timed every CALIBRATION_EVERY queries, never trained on. Always Medium:
# the reference reading has to mean the same thing in every batch.
CALIBRATION_SPEC = {"fact_table": "fact_event_m", "n_joins": 1, "has_groupby": 1,
                    "has_orderby": 0, "has_window": 0, "limit_rows": 0,
                    "filter_literal": 450}
CALIBRATION_WAREHOUSE = "Medium"
CALIBRATION_EVERY = 10

# The drift instrumentation. Not Snowflake's shape, and deliberately not
# dressed up as it: these are our numbers about our runner.
CALIBRATION_COLUMNS = [
    "query_id", "batch_name", "template_id", "template_label", "warehouse_size",
    "reps", "execution_ms", "min_execution_ms", "max_execution_ms",
    "calibration_ms", "machine_factor", "calibrated_execution_ms",
]


def machine_facts() -> dict:
    return {"cpu_count": os.cpu_count(), "duckdb_threads": DUCKDB_THREADS,
            "platform": platform.platform(), "python": platform.python_version(),
            "engine": f"duckdb-{duckdb.__version__}"}


def time_query(con, sql: str) -> dict:
    """Warm once, then repeat until the timed work is long enough to trust.

    The statement is materialised into a temporary table rather than fetched, so
    the whole result is produced -- a LIMIT is honoured, a lazy fetch is not.
    """
    con.execute(f"create or replace temp table q_result as {sql}")
    timings, spent = [], 0.0
    while len(timings) < MIN_REPS or (spent < MIN_TIMED_SECONDS and len(timings) < MAX_REPS):
        started = time.perf_counter()
        con.execute(f"create or replace temp table q_result as {sql}")
        elapsed = time.perf_counter() - started
        timings.append(elapsed)
        spent += elapsed
    return {"reps": len(timings), "median_seconds": statistics.median(timings),
            "min_seconds": min(timings), "max_seconds": max(timings)}


def compile_time_ms(con, sql: str) -> float:
    """How long the engine takes to plan the statement, in milliseconds.

    EXPLAIN parses, binds and optimises without executing, which is the same
    work Snowflake bills to COMPILATION_TIME. Three passes, median, because a
    single millisecond-scale reading is noise.
    """
    con.execute(f"explain {sql}")
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        con.execute(f"explain {sql}")
        timings.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(timings)


def partitions(con, tables: list[str]) -> int | None:
    """Row groups behind the tables a query names: DuckDB's micro-partitions."""
    total = 0
    for name in tables:
        try:
            count = con.execute(
                "select count(distinct row_group_id) from pragma_storage_info(?)",
                [name.lower()]).fetchone()[0]
        except duckdb.Error:
            return None
        total += int(count or 0)
    return total or None


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
        factor = calibration / baseline_seconds
        row["calibration_ms"] = round(calibration * 1000.0, 3)
        row["machine_factor"] = round(factor, 6)
        row["calibrated_execution_ms"] = round(row["execution_ms"] / factor, 3)


def read_batch(path: Path, limit: int | None = None) -> list[dict]:
    with open(path, newline="") as handle:
        queries = list(csv.DictReader(handle))
    return queries[:limit] if limit else queries


def history_row(query: dict, timing: dict, started_at: datetime, facts: dict,
                session_id: int, batch_name: str, tables: dict, con) -> dict:
    """One measured query, in the exact column layout of QUERY_HISTORY."""
    from .parse import parse_query_text

    text = query["query_text"]
    parsed = parse_query_text(text)
    execution_ms = timing["median_seconds"] * 1000.0
    compilation_ms = compile_time_ms(con, text)
    rows_produced = con.execute("select count(*) from q_result").fetchone()[0]
    partition_count = partitions(con, parsed["tables"])
    ended_at = started_at + timedelta(milliseconds=execution_ms + compilation_ms)

    row = snowflake.null_row()
    row.update({
        "QUERY_ID": str(uuid.uuid4()),
        "QUERY_TEXT": text,
        "DATABASE_NAME": snowflake.DATABASE_NAME,
        "SCHEMA_NAME": snowflake.SCHEMA_NAME,
        "QUERY_TYPE": "SELECT",
        "SESSION_ID": session_id,
        "USER_NAME": snowflake.USER_NAME,
        "ROLE_NAME": snowflake.ROLE_NAME,
        "WAREHOUSE_NAME": snowflake.WAREHOUSE_NAME,
        "WAREHOUSE_SIZE": query["warehouse_size"],
        "WAREHOUSE_TYPE": snowflake.WAREHOUSE_TYPE,
        "CLUSTER_NUMBER": 1,
        "QUERY_TAG": batch_name,
        "EXECUTION_STATUS": "SUCCESS",
        "START_TIME": started_at.isoformat(timespec="milliseconds"),
        "END_TIME": ended_at.isoformat(timespec="milliseconds"),
        "TOTAL_ELAPSED_TIME": round(execution_ms + compilation_ms, 3),
        "COMPILATION_TIME": round(compilation_ms, 3),
        "EXECUTION_TIME": round(execution_ms, 3),
        # Estimated, and labelled as such in the data dictionary: DuckDB does
        # not report bytes read, so this is the on-disk size of the tables the
        # statement names. The filter runs after the scan, so it does not
        # reduce it.
        "BYTES_SCANNED": sum(int(tables[name]["bytes"]) for name in parsed["tables"]
                             if name in tables) or None,
        "PARTITIONS_SCANNED": partition_count,
        "PARTITIONS_TOTAL": partition_count,
        "ROWS_PRODUCED": int(rows_produced),
        "IS_CLIENT_GENERATED_STATEMENT": "FALSE",
        "RELEASE_VERSION": facts["engine"],
        "ROLE_TYPE": "ROLE",
        "QUERY_HASH": snowflake.query_hash(text),
        "QUERY_HASH_VERSION": snowflake.HASH_VERSION,
        "QUERY_PARAMETERIZED_HASH": snowflake.parameterized_hash(text),
        "QUERY_PARAMETERIZED_HASH_VERSION": snowflake.HASH_VERSION,
        "SECONDARY_ROLE_STATS": "NONE",
        "USER_TYPE": "PERSON",
        "USER_DATABASE_NAME": snowflake.DATABASE_NAME,
        "USER_SCHEMA_NAME": snowflake.SCHEMA_NAME,
    })
    return row


def measure_batch(batch_path: Path, tables: dict, baseline_seconds: float | None = None,
                  limit: int | None = None) -> tuple[list[dict], list[dict], float]:
    """Time every query in one batch file.

    Returns the QUERY_HISTORY rows, the calibration rows beside them, and the
    reference reading that later batches are scaled back to.
    """
    facts = machine_facts()
    queries = read_batch(batch_path, limit)
    con = ensure_workload(DUCKDB_THREADS)
    session_id = int(datetime.now(UTC).timestamp())
    batch_name = batch_path.stem

    calibration_sql = sql_for(CALIBRATION_SPEC)

    def calibration_reading() -> float:
        con.execute(f"set threads={snowflake.WAREHOUSE_SIZES[CALIBRATION_WAREHOUSE]}")
        return time_query(con, calibration_sql)["median_seconds"]

    checkpoints = [(0, calibration_reading())]
    history, calibration = [], []
    for index, query in enumerate(queries):
        if index and index % CALIBRATION_EVERY == 0:
            checkpoints.append((index, calibration_reading()))
        threads = snowflake.WAREHOUSE_SIZES[query["warehouse_size"]]
        con.execute(f"set threads={threads}")
        started_at = datetime.now(UTC)
        timing = time_query(con, query["query_text"])
        row = history_row(query, timing, started_at, facts, session_id, batch_name,
                          tables, con)
        history.append(row)
        calibration.append({
            "query_id": row["QUERY_ID"], "batch_name": batch_name,
            "template_id": query["template_id"], "template_label": query["template_label"],
            "warehouse_size": query["warehouse_size"], "reps": timing["reps"],
            "execution_ms": row["EXECUTION_TIME"],
            "min_execution_ms": round(timing["min_seconds"] * 1000.0, 3),
            "max_execution_ms": round(timing["max_seconds"] * 1000.0, 3),
        })
        print(f"[measure] {index + 1:2d}/{len(queries)} {query['query_id']} "
              f"{query['warehouse_size']:>7} {row['EXECUTION_TIME']:8.1f}ms "
              f"({timing['reps']} reps) {query['template_label']}")
    checkpoints.append((len(queries), calibration_reading()))
    con.close()

    baseline = baseline_seconds or checkpoints[0][1]
    calibrate(calibration, checkpoints, baseline)
    readings = " / ".join(f"{seconds * 1000:.0f}" for _, seconds in checkpoints)
    print(f"[calibration] {readings} ms · reference {baseline * 1000:.0f} ms")
    return history, calibration, baseline
