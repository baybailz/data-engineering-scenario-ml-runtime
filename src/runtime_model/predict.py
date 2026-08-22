"""Score a query that has not been run yet. The point of the whole thing.

Two entry points, both taking shapes rather than measurements:

    predict_rows(rows)    catalogue rows -- the queue of queries waiting to be
                          measured, scored before anything executes
    predict_shape(...)    seven knobs -- table size, joins, group by, filter
                          selectivity, order by, window, limit

rows_in and bytes_est are derived here exactly as workload.py derives them for
the catalogue, from the declared table sizes and column widths. That is a
planner's estimate, available before the query starts, not a measurement.
"""

import pickle
from pathlib import Path

import numpy as np

from .features import featurise
from .workload import DIM_ROW_BYTES, DIM_ROWS, FACT_ROW_BYTES, FACT_TABLES, JOIN_DIMS

FACT_TABLE_NAMES = list(FACT_TABLES)


def load_model(path: Path) -> dict:
    """The pickle written by the last training run: model, feature order, version."""
    with open(path, "rb") as handle:
        return pickle.load(handle)


def shape_row(fact_table: str, n_joins: int, has_groupby: int, selectivity: float,
              has_orderby: int = 0, has_window: int = 0, limit_rows: int = 0) -> dict:
    """Seven knobs to the row the feature vector is built from."""
    if fact_table not in FACT_TABLES:
        raise ValueError(f"unknown table {fact_table!r}; expected one of {FACT_TABLE_NAMES}")
    n_joins = max(0, min(len(JOIN_DIMS), int(n_joins)))
    fact_rows = FACT_TABLES[fact_table]
    joined = JOIN_DIMS[:n_joins]
    return {
        "fact_table": fact_table,
        "fact_rows": fact_rows,
        "rows_in": fact_rows + sum(DIM_ROWS[dim] for dim, _, _ in joined),
        "bytes_est": fact_rows * FACT_ROW_BYTES + sum(
            DIM_ROWS[dim] * DIM_ROW_BYTES[dim] for dim, _, _ in joined),
        "n_joins": n_joins,
        "has_groupby": int(has_groupby),
        "selectivity": float(selectivity),
        "has_orderby": int(has_orderby),
        "has_window": int(has_window),
        "limit_rows": int(limit_rows),
    }


def predict_rows(model, rows: list[dict]) -> list[float]:
    """Seconds for each row. The model is fitted on log seconds, so exponentiate."""
    if not rows:
        return []
    return [float(value) for value in np.exp(model.predict(featurise(rows)))]


def predict_shape(model, **shape) -> float:
    """Seconds for one query shape described by its knobs."""
    return predict_rows(model, [shape_row(**shape)])[0]
