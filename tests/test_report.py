"""The published tables: the prediction detail, the SLA verdicts, the curve."""

import pytest

from runtime_model import report, train


@pytest.fixture
def published(measurements):
    result = train.fit(measurements)
    detail = report.prediction_detail(measurements, result["predictions"])
    history = [{column: result["metrics"][column] for column in train.MODEL_COLUMNS}]
    return {"detail": detail, "history": history, "metrics": result["metrics"]}


def test_detail_has_one_row_per_measured_query(measurements, published):
    detail = published["detail"]
    assert len(detail) == len(measurements)
    assert {row["query_id"] for row in detail} == {row["query_id"] for row in measurements}
    assert list(detail[0]) == report.DETAIL_COLUMNS


def test_detail_is_worst_first_and_carries_the_shape(published):
    errors = [row["abs_pct_error"] for row in published["detail"]]
    assert errors == sorted(errors, reverse=True)
    assert all(row["template_label"] for row in published["detail"])
    assert all(row["prediction_scope"] in ("holdout", "cross_validated")
               for row in published["detail"])


def test_detail_drops_predictions_with_no_measurement(measurements, published):
    orphan = dict(published["detail"][0])
    rows = report.prediction_detail(measurements, [
        {"query_id": "not_measured", "model_version": "v1", "actual_seconds": 1.0,
         "predicted_seconds": 1.0, "abs_pct_error": 0.0, "in_holdout": 1}])
    assert rows == []
    assert orphan["query_id"] != "not_measured"


def test_sla_verdicts_name_both_kinds_of_mistake():
    sla = 0.2
    detail = [
        {"query_id": "a", "template_id": "t1", "template_label": "slow, called",
         "actual_seconds": 0.9, "predicted_seconds": 0.8, "abs_pct_error": 11.0},
        {"query_id": "b", "template_id": "t2", "template_label": "slow, missed",
         "actual_seconds": 0.9, "predicted_seconds": 0.1, "abs_pct_error": 89.0},
        {"query_id": "c", "template_id": "t3", "template_label": "fast, false alarm",
         "actual_seconds": 0.05, "predicted_seconds": 0.5, "abs_pct_error": 900.0},
        {"query_id": "d", "template_id": "t4", "template_label": "fast, inside",
         "actual_seconds": 0.05, "predicted_seconds": 0.06, "abs_pct_error": 20.0},
    ]
    verdicts = {row["template_id"]: row["sla_verdict"] for row in report.sla_table(detail, sla)}
    assert verdicts == {"t1": "breach_called", "t2": "missed_breach",
                        "t3": "false_alarm", "t4": "inside_sla"}


def test_sla_table_aggregates_per_shape_and_sorts_worst_first(published):
    rows = report.sla_table(published["detail"])
    assert list(rows[0]) == report.SLA_COLUMNS
    assert sum(row["queries"] for row in rows) == len(published["detail"])
    worst = [row["worst_actual_seconds"] for row in rows]
    assert worst == sorted(worst, reverse=True)
    assert all(row["sla_seconds"] == report.SLA_SECONDS for row in rows)


def test_model_versions_is_the_learning_curve(published):
    history = published["history"] * 1
    second = dict(history[0], model_version="v2-beef", holdout_mape_pct=9.0,
                  baseline_mape_pct=21.0, passes_gate=True)
    rows = report.model_versions(history + [second])
    assert [row["model_sequence"] for row in rows] == [1, 2]
    assert rows[0]["mape_change"] is None
    assert rows[1]["mape_change"] == pytest.approx(9.0 - history[0]["holdout_mape_pct"], abs=1e-6)
    assert rows[1]["mape_gain_over_baseline"] == pytest.approx(12.0)
    assert rows[1]["gate_status"] == "pass"


def test_a_failing_model_is_still_published_and_labelled(published):
    failed = dict(published["history"][0], passes_gate=False)
    rows = report.model_versions([failed])
    assert len(rows) == 1
    assert rows[0]["gate_status"] == "fail"


def test_checks_pass_on_a_clean_run(measurements, published):
    versions = report.model_versions(published["history"])
    results = report.checks(measurements, published["detail"], versions)
    assert all(result["ok"] for result in results), [r for r in results if not r["ok"]]


def test_checks_catch_a_missing_prediction(measurements, published):
    versions = report.model_versions(published["history"])
    results = report.checks(measurements, published["detail"][1:], versions)
    failed = [result["check"] for result in results if not result["ok"]]
    assert "every measured query has a prediction" in failed


def test_checks_catch_a_negative_prediction(measurements, published):
    broken = [dict(published["detail"][0], predicted_seconds=-1.0)] + published["detail"][1:]
    versions = report.model_versions(published["history"])
    failed = [result["check"] for result in report.checks(measurements, broken, versions)
              if not result["ok"]]
    assert "no prediction is zero or negative" in failed


def test_model_card_reports_the_gate_and_the_interval(published):
    card = report.model_card(published["metrics"])
    assert published["metrics"]["model_version"] in card
    assert "95% CI" in card
    assert ("PASS" if published["metrics"]["passes_gate"] else "FAIL") in card
    assert "## Limits" in card
    assert card.count("| feature | importance |") == 1
