"""Calibration: the part that decides whether the measurements mean anything.

A runner that slows down halfway through a batch must not look like a batch of
slower queries. These tests pin the interpolation and the scaling without
timing anything.
"""

import pytest

from runtime_model.measure import calibrate, interpolate


def test_interpolation_between_checkpoints():
    checkpoints = [(0, 0.10), (10, 0.20)]
    assert interpolate(checkpoints, 0) == pytest.approx(0.10)
    assert interpolate(checkpoints, 5) == pytest.approx(0.15)
    assert interpolate(checkpoints, 10) == pytest.approx(0.20)


def test_interpolation_past_the_last_checkpoint_holds_the_last_reading():
    assert interpolate([(0, 0.1), (10, 0.3)], 40) == pytest.approx(0.3)


def test_repeated_checkpoint_position_does_not_divide_by_zero():
    assert interpolate([(0, 0.1), (0, 0.1), (4, 0.2)], 0) == pytest.approx(0.1)


def make_rows(*milliseconds):
    return [{"execution_ms": value} for value in milliseconds]


def test_a_runner_that_doubles_in_speed_is_divided_out():
    """Both queries were equally expensive; only the machine changed."""
    rows = make_rows(400.0, 800.0)
    calibrate(rows, [(0, 0.10), (1, 0.20)], baseline_seconds=0.10)
    assert rows[0]["calibrated_execution_ms"] == pytest.approx(400.0)
    assert rows[1]["calibrated_execution_ms"] == pytest.approx(400.0)


def test_a_steady_runner_leaves_the_reading_alone():
    rows = make_rows(250.0, 750.0)
    calibrate(rows, [(0, 0.10), (2, 0.10)], baseline_seconds=0.10)
    assert [row["calibrated_execution_ms"] for row in rows] == pytest.approx([250.0, 750.0])
    assert all(row["machine_factor"] == 1.0 for row in rows)


def test_the_baseline_is_the_first_batch_not_this_batch():
    """A later batch measured on a slower machine is scaled back to the first."""
    rows = make_rows(200.0)
    calibrate(rows, [(0, 0.20), (1, 0.20)], baseline_seconds=0.10)
    assert rows[0]["machine_factor"] == pytest.approx(2.0)
    assert rows[0]["calibrated_execution_ms"] == pytest.approx(100.0)


def test_the_drift_factor_has_no_snowflake_column():
    """It is our instrumentation, so it is published in its own table."""
    from runtime_model import snowflake
    from runtime_model.measure import CALIBRATION_COLUMNS

    assert "machine_factor" in CALIBRATION_COLUMNS
    assert not set(CALIBRATION_COLUMNS) & set(snowflake.QUERY_HISTORY_COLUMNS)
