"""Synthetic measurements. Small, deterministic, and shaped like the real ones.

The tests must not need a measurement run: timing 240 queries takes minutes and
would make the suite a benchmark rather than a test. So the fixtures build rows
with a known runtime law -- runtime rises with rows scanned and with joins --
and the tests check that the code around the model behaves, not that the model
is accurate on invented data.
"""

import numpy as np
import pytest

from runtime_model.workload import DIM_ROWS, FACT_ROW_BYTES, FACT_TABLES, JOIN_DIMS


def synthetic_row(index: int, batch_name: str, rng: np.random.Generator) -> dict:
    """One measured query, with a runtime that follows a fixed, learnable law."""
    table = list(FACT_TABLES)[index % len(FACT_TABLES)]
    fact_rows = FACT_TABLES[table]
    n_joins = index % 4
    has_groupby = (index // 2) % 2
    has_orderby = (index // 3) % 2
    has_window = (index // 5) % 2
    selectivity = [0.02, 0.15, 0.45, 0.90][index % 4]
    limit_rows = [0, 100, 1000][index % 3]
    joined = JOIN_DIMS[:n_joins]

    seconds = (fact_rows / 5e7) * (1 + 0.35 * n_joins) * (1 + 0.5 * selectivity)
    seconds *= (1 + 0.4 * has_groupby) * (1 + 0.6 * has_window)
    seconds *= float(np.exp(rng.normal(0, 0.03)))
    return {
        "batch_name": batch_name,
        "query_id": f"q{index:03d}",
        "template_id": f"t{index % 12:02d}",
        "template_label": f"{fact_rows / 1e6:.0f}M rows · {n_joins} joins",
        "fact_table": table,
        "fact_rows": fact_rows,
        "rows_in": fact_rows + sum(DIM_ROWS[dim] for dim, _, _ in joined),
        "bytes_est": fact_rows * FACT_ROW_BYTES,
        "n_joins": n_joins,
        "has_groupby": has_groupby,
        "selectivity": selectivity,
        "has_orderby": has_orderby,
        "has_window": has_window,
        "limit_rows": limit_rows,
        "reps": 7,
        "median_seconds": round(seconds, 6),
        "min_seconds": round(seconds * 0.97, 6),
        "max_seconds": round(seconds * 1.06, 6),
        "calibration_seconds": 0.1,
        "machine_factor": 1.0,
        "normalized_seconds": round(seconds, 6),
        "cpu_count": 4,
        "duckdb_threads": 4,
        "measured_at": "2026-08-21T12:00:00+00:00",
    }


@pytest.fixture
def measurements() -> list[dict]:
    """Two batches, so the holdout is a whole batch as it is in a real run."""
    rng = np.random.default_rng(7)
    return ([synthetic_row(i, "batch_01", rng) for i in range(48)]
            + [synthetic_row(i, "batch_02", rng) for i in range(48, 96)])
