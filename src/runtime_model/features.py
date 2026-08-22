"""The feature vector. One definition, used by training and by scoring.

Every feature comes from a column that exists the moment the statement is
submitted: the text of the query, the warehouse it was sent to, the size of the
tables it names, and what the same query shape cost the last time it ran. That
is the whole constraint. BYTES_SCANNED, PARTITIONS_SCANNED, ROWS_PRODUCED and
every *_TIME column are written by the engine after the query has finished, so
using one would make the model useless for the thing it is for -- deciding what
to do with a query that has not started.

The constraint is enforced here rather than promised in a comment.
`featurise` projects each row down to SOURCE_COLUMNS + HISTORY_COLUMNS before
it builds anything, so an after-the-fact column is not merely unused: it is not
in the dictionary the builder can see. tests/test_leakage.py checks that
projection against the QUERY_HISTORY column list.

The order of FEATURES is the column order of the matrix, of the ONNX input and
of the controls in the page's try-it widget. Change it in one place or not at all.
"""

import numpy as np

from .parse import shape

# Read straight out of QUERY_HISTORY. Both are in snowflake.PRE_RUN_COLUMNS.
SOURCE_COLUMNS = ["QUERY_TEXT", "WAREHOUSE_SIZE"]
# Derived from earlier batches only, never from the row being scored.
HISTORY_COLUMNS = ["PRIOR_EXECUTION_MS", "HAS_PRIOR"]
# What building the two above is allowed to read. Also pre-run columns.
HISTORY_SOURCE_COLUMNS = ["QUERY_TAG", "QUERY_PARAMETERIZED_HASH"]

FEATURES = ["log_table_rows", "log_table_bytes", "n_tables", "n_joins",
            "has_group_by", "has_order_by", "has_window", "log_limit_rows",
            "n_predicates", "predicate_literal", "warehouse_threads",
            "has_prior", "log_prior_ms"]


def feature_row(row: dict, tables: dict) -> list[float]:
    """One pre-run row to one feature vector, in FEATURES order."""
    parsed = shape(row.get("QUERY_TEXT", ""), row.get("WAREHOUSE_SIZE", ""), tables)
    has_prior = float(row.get("HAS_PRIOR") or 0)
    prior_ms = float(row.get("PRIOR_EXECUTION_MS") or 0.0)
    return [
        np.log10(max(parsed["table_rows"], 1)),
        np.log10(max(parsed["table_bytes"], 1)),
        float(parsed["n_tables"]),
        float(parsed["n_joins"]),
        float(parsed["has_group_by"]),
        float(parsed["has_order_by"]),
        float(parsed["has_window"]),
        np.log10(float(parsed["limit_rows"]) + 1.0),
        float(parsed["n_predicates"]),
        float(parsed["predicate_literal"]),
        float(parsed["warehouse_threads"]),
        has_prior,
        np.log10(prior_ms + 1.0) if has_prior else 0.0,
    ]


def project(row: dict) -> dict:
    """The only columns the feature builder is allowed to see."""
    return {column: row.get(column)
            for column in SOURCE_COLUMNS + HISTORY_COLUMNS if column in row}


def featurise(rows: list[dict], tables: dict) -> np.ndarray:
    """The feature matrix for a list of rows, in FEATURES order."""
    return np.asarray([feature_row(project(row), tables) for row in rows], dtype=float)


def attach_history(rows: list[dict]) -> list[dict]:
    """Fill PRIOR_EXECUTION_MS from earlier batches, and only earlier batches.

    "Have we run this shape before, and what did it cost" is a real pre-run
    signal: QUERY_PARAMETERIZED_HASH is the same query with its literals
    replaced, so the four filter constants of one template share it. The
    lookback is whole batches, so a query is never informed by a query measured
    beside it -- including, in particular, by the holdout batch it belongs to.
    """
    seen: dict[str, list[float]] = {}
    ordered = sorted({row.get("QUERY_TAG") for row in rows}, key=lambda tag: str(tag))
    for tag in ordered:
        batch = [row for row in rows if row.get("QUERY_TAG") == tag]
        for row in batch:
            past = seen.get(row.get("QUERY_PARAMETERIZED_HASH"), [])
            row["HAS_PRIOR"] = 1 if past else 0
            row["PRIOR_EXECUTION_MS"] = round(float(np.mean(past)), 3) if past else None
        for row in batch:
            seen.setdefault(row.get("QUERY_PARAMETERIZED_HASH"), []).append(
                float(row["TARGET_MS"]))
    return rows


def history_index(rows: list[dict]) -> dict:
    """Mean past runtime per query shape, over everything measured so far."""
    seen: dict[str, list[float]] = {}
    for row in rows:
        seen.setdefault(row.get("QUERY_PARAMETERIZED_HASH"), []).append(
            float(row["TARGET_MS"]))
    return {key: round(float(np.mean(values)), 3) for key, values in seen.items()}


def attach_prior(rows: list[dict], index: dict) -> list[dict]:
    """The same lookup for a query that has not run: the queue, or the widget."""
    for row in rows:
        prior = index.get(row.get("QUERY_PARAMETERIZED_HASH"))
        row["HAS_PRIOR"] = 1 if prior else 0
        row["PRIOR_EXECUTION_MS"] = prior
    return rows
