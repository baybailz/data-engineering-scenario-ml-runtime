"""Score a query that has not been run yet. The point of the whole thing.

The input is the same handful of pre-run columns the training rows were built
from: the SQL text, the warehouse it would be sent to, and -- if the same
parameterised shape has been measured before -- what it cost then. Nothing here
touches a measurement of the query being scored, because there is not one.

    queue_rows(rows, index)   the queue: catalogue rows with a prior attached
    predict_rows(...)         milliseconds for a list of pre-run rows
    predict_text(...)         milliseconds for one statement and one warehouse
"""

import pickle
from pathlib import Path

import numpy as np

from .features import featurise
from .snowflake import WAREHOUSE_SIZES, parameterized_hash


def load_model(path: Path) -> dict:
    """The pickle written by the last training run: model, feature order, version."""
    with open(path, "rb") as handle:
        return pickle.load(handle)


def pre_run_row(query_text: str, warehouse_size: str) -> dict:
    """A statement and a warehouse, in the column names QUERY_HISTORY uses."""
    if warehouse_size not in WAREHOUSE_SIZES:
        raise ValueError(f"unknown warehouse size {warehouse_size!r}; "
                         f"expected one of {list(WAREHOUSE_SIZES)}")
    return {"QUERY_TEXT": query_text, "WAREHOUSE_SIZE": warehouse_size,
            "QUERY_PARAMETERIZED_HASH": parameterized_hash(query_text)}


def queue_rows(rows: list[dict], index: dict | None = None) -> list[dict]:
    """Catalogue rows from incoming/batch_*.csv as pre-run rows, priors filled."""
    from .features import attach_prior

    built = [pre_run_row(row["query_text"], row["warehouse_size"]) for row in rows]
    return attach_prior(built, index or {})


def predict_rows(model, rows: list[dict], tables: dict) -> list[float]:
    """Milliseconds for each row. The model is fitted on log ms, so exponentiate."""
    if not rows:
        return []
    return [float(value) for value in np.exp(model.predict(featurise(rows, tables)))]


def predict_text(model, query_text: str, warehouse_size: str, tables: dict,
                 index: dict | None = None) -> float:
    """Milliseconds for one statement on one warehouse size."""
    from .features import attach_prior

    row = attach_prior([pre_run_row(query_text, warehouse_size)], index or {})[0]
    return predict_rows(model, [row], tables)[0]
