"""Metrics, the holdout split, the gate, and the ONNX copy of the model."""

import numpy as np
import pytest

from runtime_model import train
from runtime_model.features import FEATURES


def test_mape_is_a_percentage():
    actual = np.array([1.0, 2.0, 4.0])
    assert train.mape(actual, actual) == pytest.approx(0.0)
    assert train.mape(actual, actual * 1.1) == pytest.approx(10.0)


def test_r_squared():
    actual = np.array([1.0, 2.0, 3.0, 4.0])
    assert train.r_squared(actual, actual) == pytest.approx(1.0)
    assert train.r_squared(actual, np.full(4, actual.mean())) == pytest.approx(0.0)


def test_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(1)
    actual = rng.uniform(0.05, 1.0, 200)
    predicted = actual * rng.normal(1.0, 0.1, 200)
    low, high = train.bootstrap_mape_ci(actual, predicted)
    assert low < train.mape(actual, predicted) < high


def test_the_gate_is_both_conditions():
    assert train.passes_gate(10.0, 0.95)
    assert not train.passes_gate(20.0, 0.95)
    assert not train.passes_gate(10.0, 0.50)
    assert train.passes_gate(train.GATE_MAPE_PCT, train.GATE_R2)


def test_holdout_is_the_most_recent_batch(measurements):
    _, holdout = train.split(measurements)
    assert {measurements[i]["batch_name"] for i in holdout} == {"batch_02"}


def test_holdout_is_the_tail_when_there_is_only_one_batch(measurements):
    single = [row for row in measurements if row["batch_name"] == "batch_01"]
    trained, holdout = train.split(single)
    assert set(trained) & set(holdout) == set()
    assert holdout == list(range(len(trained), len(single)))


def test_too_few_rows_refuses_to_train(measurements):
    with pytest.raises(ValueError):
        train.fit(measurements[:5])


def test_fit_scores_out_of_sample_and_gates(measurements):
    result = train.fit(measurements)
    metrics = result["metrics"]
    assert metrics["n_train_rows"] + metrics["n_holdout_rows"] == len(measurements)
    assert metrics["mape_ci_low_pct"] <= metrics["holdout_mape_pct"] <= metrics["mape_ci_high_pct"]
    assert metrics["passes_gate"] == train.passes_gate(metrics["holdout_mape_pct"],
                                                       metrics["holdout_r2"])
    assert {row["feature"] for row in metrics["importances"]} == set(FEATURES)
    assert len(result["predictions"]) == len(measurements)
    assert all(row["predicted_seconds"] > 0 for row in result["predictions"])
    assert sum(row["in_holdout"] for row in result["predictions"]) == metrics["n_holdout_rows"]


def test_version_number_increments_and_carries_a_digest(measurements):
    first = train.version_for(measurements, [])
    assert first.startswith("v1-")
    assert train.version_for(measurements, [{"model_version": first}]).startswith("v2-")
    changed = [dict(measurements[0], median_seconds=99.0)] + measurements[1:]
    assert train.version_for(changed, []) != first


def test_calibration_table_covers_every_holdout_row():
    actual = np.linspace(0.05, 1.0, 40)
    table = train.calibration_table(actual, actual * 1.05)
    assert sum(row["queries"] for row in table) == 40
    assert [row["decile"] for row in table] == list(range(1, len(table) + 1))


def test_onnx_export_agrees_with_sklearn(measurements, tmp_path):
    """The page runs the ONNX copy. If it disagreed, the page would lie."""
    result = train.fit(measurements)
    onnx_path, meta_path = tmp_path / "model.onnx", tmp_path / "model_meta.json"
    max_diff = train.export_onnx(result["model"], result["features"], result["metrics"],
                                 onnx_path, meta_path)
    assert max_diff < train.ONNX_TOLERANCE
    assert onnx_path.stat().st_size > 0

    import json

    meta = json.loads(meta_path.read_text())
    assert meta["features"] == FEATURES
    assert meta["model_version"] == result["metrics"]["model_version"]
    assert set(meta["feature_ranges"]) == set(FEATURES)
    assert [table["name"] for table in meta["catalogue"]["fact_tables"]]
