"""The guard: nothing the engine wrote after the query finished reaches the model.

A runtime model that is allowed to see BYTES_SCANNED or ROWS_PRODUCED scores
beautifully and is worthless, because neither number exists when the decision
has to be made. These tests are the reason the projection in features.py is
code rather than a comment.
"""

import numpy as np

from runtime_model import snowflake
from runtime_model.features import (
    FEATURES,
    HISTORY_COLUMNS,
    HISTORY_SOURCE_COLUMNS,
    SOURCE_COLUMNS,
    attach_history,
    featurise,
    project,
)

BANNED_WORDS = {"bytes_scanned", "partitions_scanned", "partitions_total",
                "rows_produced", "rows_inserted", "execution_time", "elapsed",
                "compilation", "queued", "spilled", "cache", "credits",
                "query_load", "acceleration", "retry", "fault"}


def test_the_two_column_sets_partition_query_history():
    assert set(snowflake.PRE_RUN_COLUMNS) <= set(snowflake.QUERY_HISTORY_COLUMNS)
    assert set(snowflake.AFTER_THE_FACT_COLUMNS) <= set(snowflake.QUERY_HISTORY_COLUMNS)
    assert set(snowflake.PRE_RUN_COLUMNS) & set(snowflake.AFTER_THE_FACT_COLUMNS) == set()
    assert (set(snowflake.PRE_RUN_COLUMNS) | set(snowflake.AFTER_THE_FACT_COLUMNS)
            == set(snowflake.QUERY_HISTORY_COLUMNS))


def test_the_target_and_its_neighbours_are_after_the_fact():
    for column in ("EXECUTION_TIME", "TOTAL_ELAPSED_TIME", "COMPILATION_TIME",
                   "BYTES_SCANNED", "PARTITIONS_SCANNED", "PARTITIONS_TOTAL",
                   "ROWS_PRODUCED", "PERCENTAGE_SCANNED_FROM_CACHE",
                   "BYTES_SPILLED_TO_LOCAL_STORAGE", "QUEUED_OVERLOAD_TIME",
                   "QUERY_LOAD_PERCENT", "END_TIME"):
        assert column in snowflake.AFTER_THE_FACT_COLUMNS


def test_the_feature_builder_reads_only_pre_run_columns():
    assert set(SOURCE_COLUMNS) <= set(snowflake.PRE_RUN_COLUMNS)
    assert set(HISTORY_SOURCE_COLUMNS) <= set(snowflake.PRE_RUN_COLUMNS)
    assert set(SOURCE_COLUMNS) & set(snowflake.AFTER_THE_FACT_COLUMNS) == set()
    # The two history columns are ours, not Snowflake's, and are built from
    # earlier batches by attach_history.
    assert set(HISTORY_COLUMNS) & set(snowflake.QUERY_HISTORY_COLUMNS) == set()


def test_no_feature_is_named_after_something_measured():
    for name in FEATURES:
        assert not any(word in name.lower() for word in BANNED_WORDS), name


def test_the_projection_drops_every_after_the_fact_column(measurements):
    visible = project(measurements[0])
    assert set(visible) == set(SOURCE_COLUMNS + HISTORY_COLUMNS)
    for column in snowflake.AFTER_THE_FACT_COLUMNS:
        assert column not in visible


def test_deleting_the_measurements_does_not_move_a_single_feature(measurements, tables):
    """The proof: blank every after-the-fact column and refeaturise."""
    blinded = [{key: (None if key in snowflake.AFTER_THE_FACT_COLUMNS else value)
                for key, value in row.items()} for row in measurements]
    assert np.array_equal(featurise(measurements, tables), featurise(blinded, tables))


def test_a_prior_never_comes_from_the_batch_it_is_in():
    """The first batch has no history, so nothing in it can have a prior."""
    rows = [{"QUERY_TAG": tag, "QUERY_PARAMETERIZED_HASH": "same", "TARGET_MS": 10.0}
            for tag in ("batch_01", "batch_01", "batch_02", "batch_02")]
    attach_history(rows)
    assert [row["HAS_PRIOR"] for row in rows] == [0, 0, 1, 1]
    assert [row["PRIOR_EXECUTION_MS"] for row in rows] == [None, None, 10.0, 10.0]


def test_a_prior_is_the_mean_of_the_batches_before_it():
    rows = [{"QUERY_TAG": "batch_01", "QUERY_PARAMETERIZED_HASH": "a", "TARGET_MS": 10.0},
            {"QUERY_TAG": "batch_02", "QUERY_PARAMETERIZED_HASH": "a", "TARGET_MS": 30.0},
            {"QUERY_TAG": "batch_03", "QUERY_PARAMETERIZED_HASH": "a", "TARGET_MS": 99.0},
            {"QUERY_TAG": "batch_03", "QUERY_PARAMETERIZED_HASH": "b", "TARGET_MS": 99.0}]
    attach_history(rows)
    assert rows[2]["PRIOR_EXECUTION_MS"] == 20.0
    assert rows[3]["HAS_PRIOR"] == 0
