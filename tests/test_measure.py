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


def make_rows(*seconds):
    return [{"median_seconds": value} for value in seconds]


def test_a_runner_that_doubles_in_speed_is_divided_out():
    """Both queries were equally expensive; only the machine changed."""
    rows = make_rows(0.40, 0.80)
    calibrate(rows, [(0, 0.10), (1, 0.20)], baseline_seconds=0.10)
    assert rows[0]["normalized_seconds"] == pytest.approx(0.40)
    assert rows[1]["normalized_seconds"] == pytest.approx(0.40)


def test_a_steady_runner_leaves_the_reading_alone():
    rows = make_rows(0.25, 0.75)
    calibrate(rows, [(0, 0.10), (2, 0.10)], baseline_seconds=0.10)
    assert [row["normalized_seconds"] for row in rows] == pytest.approx([0.25, 0.75])
    assert all(row["machine_factor"] == 1.0 for row in rows)


def test_the_baseline_is_the_first_batch_not_this_batch():
    """A later batch measured on a slower machine is scaled back to the first."""
    rows = make_rows(0.20)
    calibrate(rows, [(0, 0.20), (1, 0.20)], baseline_seconds=0.10)
    assert rows[0]["machine_factor"] == pytest.approx(2.0)
    assert rows[0]["normalized_seconds"] == pytest.approx(0.10)
