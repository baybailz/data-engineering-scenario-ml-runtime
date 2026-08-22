"""The feature vector. One definition, used by training and by scoring.

Every feature is knowable before the query runs. That is the whole constraint:
a feature that is only readable afterwards -- rows returned, bytes spilled,
time in the hash join -- would make the model useless for the thing it is for,
which is deciding what to do with a query you have not run yet.

The order of FEATURES is the column order of the matrix, of the ONNX input and
of the sliders in the page's try-it widget. Change it in one place or not at all.
"""

import numpy as np

FEATURES = ["log_rows_in", "log_bytes_est", "log_rows_after_filter", "n_joins",
            "has_groupby", "selectivity", "has_orderby", "has_window", "log_limit_rows"]


def feature_row(row: dict) -> list[float]:
    """One catalogue row (or one hand-built query shape) to one feature vector."""
    fact_rows = float(row["fact_rows"])
    selectivity = float(row["selectivity"])
    return [
        np.log10(float(row["rows_in"])),
        np.log10(float(row["bytes_est"])),
        np.log10(max(fact_rows * selectivity, 1.0)),
        float(row["n_joins"]),
        float(row["has_groupby"]),
        selectivity,
        float(row["has_orderby"]),
        float(row["has_window"]),
        np.log10(float(row["limit_rows"]) + 1.0),
    ]


def featurise(rows: list[dict]) -> np.ndarray:
    """The feature matrix for a list of rows, in FEATURES order."""
    return np.asarray([feature_row(row) for row in rows], dtype=float)
