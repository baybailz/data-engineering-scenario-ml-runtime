"""The feature vector: order, transforms, and where each number comes from."""

import numpy as np
import pytest

from runtime_model.features import FEATURES, attach_prior, feature_row, featurise, history_index
from runtime_model.parse import shape
from runtime_model.predict import pre_run_row
from runtime_model.workload import sql_for

SPEC = {"fact_table": "fact_event_m", "n_joins": 1, "has_groupby": 1, "has_orderby": 0,
        "has_window": 0, "limit_rows": 0, "filter_literal": 450}


def test_feature_order_is_the_contract():
    assert FEATURES == ["log_table_rows", "log_table_bytes", "n_tables", "n_joins",
                        "has_group_by", "has_order_by", "has_window", "log_limit_rows",
                        "n_predicates", "predicate_literal", "warehouse_threads",
                        "has_prior", "log_prior_ms"]


def test_a_query_and_a_warehouse_are_the_whole_input(tables):
    """Two pre-run columns in, one vector out. Nothing measured is involved."""
    row = pre_run_row(sql_for(SPEC), "Small")
    vector = feature_row(row, tables)
    assert len(vector) == len(FEATURES)
    parsed = shape(sql_for(SPEC), "Small", tables)
    assert vector[0] == pytest.approx(np.log10(parsed["table_rows"]))
    assert vector[1] == pytest.approx(np.log10(parsed["table_bytes"]))
    assert vector[FEATURES.index("warehouse_threads")] == 2.0
    assert vector[FEATURES.index("predicate_literal")] == 450.0


def test_warehouse_size_is_the_only_thing_that_moves(tables):
    small = feature_row(pre_run_row(sql_for(SPEC), "X-Small"), tables)
    medium = feature_row(pre_run_row(sql_for(SPEC), "Medium"), tables)
    index = FEATURES.index("warehouse_threads")
    assert small[index] == 1.0 and medium[index] == 4.0
    assert small[:index] == medium[:index]


def test_no_limit_does_not_blow_up(tables):
    """log(0) is not a number; log(limit + 1) is, and 'no limit' is limit 0."""
    row = pre_run_row(sql_for(dict(SPEC, limit_rows=0)), "Medium")
    assert feature_row(row, tables)[FEATURES.index("log_limit_rows")] == 0.0


def test_a_query_with_no_prior_scores_a_zero_not_a_hole(tables):
    row = pre_run_row(sql_for(SPEC), "Medium")
    vector = feature_row(row, tables)
    assert vector[FEATURES.index("has_prior")] == 0.0
    assert vector[FEATURES.index("log_prior_ms")] == 0.0
    assert not any(np.isnan(vector))


def test_a_prior_arrives_through_the_parameterized_hash(tables):
    """The same shape with a different constant is the same parameterized hash."""
    measured = [{"QUERY_PARAMETERIZED_HASH":
                 pre_run_row(sql_for(SPEC), "Medium")["QUERY_PARAMETERIZED_HASH"],
                 "TARGET_MS": 999.0}]
    other = dict(SPEC, filter_literal=900)
    row = attach_prior([pre_run_row(sql_for(other), "Medium")],
                       history_index(measured))[0]
    assert row["HAS_PRIOR"] == 1
    assert row["PRIOR_EXECUTION_MS"] == 999.0
    assert feature_row(row, tables)[FEATURES.index("log_prior_ms")] == pytest.approx(
        np.log10(1000.0))


def test_featurise_shape(measurements, tables):
    assert featurise(measurements, tables).shape == (len(measurements), len(FEATURES))


def test_string_input_is_accepted(measurements, tables):
    """Rows arrive from CSV, where everything is a string."""
    row = measurements[0]
    as_text = {key: ("" if value is None else str(value)) for key, value in row.items()}
    assert feature_row(as_text, tables) == pytest.approx(feature_row(row, tables))
