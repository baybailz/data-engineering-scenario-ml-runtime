"""The feature vector: order, transforms, and the promise that it is pre-run."""

import numpy as np
import pytest

from runtime_model.features import FEATURES, feature_row, featurise
from runtime_model.predict import shape_row


def test_feature_order_is_the_contract():
    assert FEATURES == ["log_rows_in", "log_bytes_est", "log_rows_after_filter", "n_joins",
                        "has_groupby", "selectivity", "has_orderby", "has_window",
                        "log_limit_rows"]


def test_every_feature_is_known_before_the_query_runs():
    """No feature may be derived from a measurement. That is the whole design."""
    measured = {"reps", "median_seconds", "min_seconds", "max_seconds",
                "normalized_seconds", "calibration_seconds", "machine_factor"}
    row = shape_row("fact_event_m", n_joins=1, has_groupby=1, selectivity=0.45)
    assert not measured & set(row)
    assert len(feature_row(row)) == len(FEATURES)


def test_log_transforms(measurements):
    row = measurements[0]
    vector = feature_row(row)
    assert vector[0] == pytest.approx(np.log10(row["rows_in"]))
    assert vector[1] == pytest.approx(np.log10(row["bytes_est"]))
    assert vector[2] == pytest.approx(np.log10(row["fact_rows"] * row["selectivity"]))


def test_limit_of_zero_does_not_blow_up():
    """log(0) is not a number; log(limit + 1) is, and 'no limit' is limit 0."""
    row = shape_row("fact_event_s", n_joins=0, has_groupby=0, selectivity=0.1, limit_rows=0)
    assert feature_row(row)[-1] == 0.0


def test_string_input_is_accepted():
    """Rows arrive from CSV, where everything is a string."""
    row = shape_row("fact_event_l", n_joins=2, has_groupby=1, selectivity=0.45)
    as_text = {key: str(value) for key, value in row.items()}
    assert feature_row(as_text) == pytest.approx(feature_row(row))


def test_featurise_shape(measurements):
    assert featurise(measurements).shape == (len(measurements), len(FEATURES))


def test_shape_row_derives_the_catalogue_geometry():
    """rows_in and bytes_est must match what workload.py wrote into the catalogue."""
    none = shape_row("fact_event_m", n_joins=0, has_groupby=0, selectivity=0.45)
    three = shape_row("fact_event_m", n_joins=3, has_groupby=0, selectivity=0.45)
    assert three["rows_in"] > none["rows_in"]
    assert three["bytes_est"] > none["bytes_est"]
    assert none["rows_in"] == none["fact_rows"]


def test_shape_row_clamps_joins_and_rejects_unknown_tables():
    assert shape_row("fact_event_s", n_joins=9, has_groupby=0, selectivity=0.1)["n_joins"] == 3
    with pytest.raises(ValueError):
        shape_row("fact_event_nope", n_joins=0, has_groupby=0, selectivity=0.1)
