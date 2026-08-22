"""Synthetic QUERY_HISTORY. Small, deterministic, and shaped like the real thing.

The tests must not need a measurement run: timing 240 queries takes minutes and
would make the suite a benchmark rather than a test. So the fixtures take real
catalogue queries -- real SQL text, real warehouse sizes -- and give each one a
runtime from a fixed law: it rises with the rows behind the tables it names and
with the joins, and falls with the threads the warehouse has. The tests then
check that the code around the model behaves, not that the model is accurate on
invented data.
"""

import csv

import numpy as np
import pytest

from runtime_model import snowflake
from runtime_model.features import attach_history
from runtime_model.parse import shape, table_index
from runtime_model.workload import ROOT, catalogue

BATCH = 48


@pytest.fixture(scope="session")
def tables() -> dict:
    """The committed ACCOUNT_USAGE.TABLES copy, as the parser wants it."""
    with open(ROOT / "data" / "tables.csv", newline="") as handle:
        return table_index(list(csv.DictReader(handle)))


def synthetic_row(query: dict, batch_name: str, tables: dict,
                  rng: np.random.Generator) -> dict:
    """One measured query in QUERY_HISTORY shape, with a learnable runtime."""
    parsed = shape(query["query_text"], query["warehouse_size"], tables)
    milliseconds = parsed["table_rows"] / 5e4 / max(parsed["warehouse_threads"], 1)
    milliseconds *= (1 + 0.35 * parsed["n_joins"])
    milliseconds *= (1 + 0.5 * parsed["predicate_literal"] / 1000.0)
    milliseconds *= (1 + 0.4 * parsed["has_group_by"]) * (1 + 0.6 * parsed["has_window"])
    milliseconds *= float(np.exp(rng.normal(0, 0.03)))

    row = snowflake.null_row()
    row.update({
        "QUERY_ID": f"{batch_name}-{query['query_id']}",
        "QUERY_TEXT": query["query_text"],
        "QUERY_TYPE": "SELECT",
        "WAREHOUSE_NAME": snowflake.WAREHOUSE_NAME,
        "WAREHOUSE_SIZE": query["warehouse_size"],
        "QUERY_TAG": batch_name,
        "EXECUTION_STATUS": "SUCCESS",
        "EXECUTION_TIME": round(milliseconds, 3),
        "TOTAL_ELAPSED_TIME": round(milliseconds + 2.0, 3),
        "COMPILATION_TIME": 2.0,
        "ROWS_PRODUCED": 1000,
        "RELEASE_VERSION": "duckdb-1.3.2",
        "QUERY_HASH": snowflake.query_hash(query["query_text"]),
        "QUERY_PARAMETERIZED_HASH": snowflake.parameterized_hash(query["query_text"]),
    })
    row.update({"TARGET_MS": round(milliseconds, 3), "MACHINE_FACTOR": 1.0, "REPS": 7,
                "TEMPLATE_ID": query["template_id"],
                "TEMPLATE_LABEL": query["template_label"]})
    return row


@pytest.fixture(scope="session")
def measurements(tables) -> list[dict]:
    """Two batches, so the holdout is a whole batch as it is in a real run."""
    rng = np.random.default_rng(7)
    queries = catalogue()[: 2 * BATCH]
    rows = [synthetic_row(query, "batch_01", tables, rng) for query in queries[:BATCH]]
    rows += [synthetic_row(query, "batch_02", tables, rng) for query in queries[BATCH:]]
    return attach_history(rows)
