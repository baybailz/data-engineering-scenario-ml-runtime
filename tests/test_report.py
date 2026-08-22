"""The published tables: the prediction detail, the SLA verdicts, the curve."""

import pytest

from runtime_model import report, train


@pytest.fixture(scope="module")
def published(measurements, tables):
    result = train.fit(measurements, tables)
    detail = report.prediction_detail(measurements, result["predictions"], tables)
    history = [{column: result["metrics"][column] for column in train.MODEL_COLUMNS}]
    return {"detail": detail, "history": history, "metrics": result["metrics"]}


def test_the_shape_columns_are_parsed_back_out_of_the_sql(measurements, published, tables):
    """What the table shows is what the model saw, not a column carried beside it."""
    row = published["detail"][0]
    source = next(r for r in measurements if r["QUERY_ID"] == row["query_id"])
    parsed = report.describe(source, tables)
    assert row["n_joins"] == parsed["n_joins"]
    assert row["table_rows"] == parsed["table_rows"]
    assert row["warehouse_size"] == source["WAREHOUSE_SIZE"]


def test_detail_has_one_row_per_measured_query(measurements, published):
    detail = published["detail"]
    assert len(detail) == len(measurements)
    assert {row["query_id"] for row in detail} == {row["QUERY_ID"] for row in measurements}
    assert list(detail[0]) == report.DETAIL_COLUMNS


def test_detail_is_worst_first_and_carries_the_shape(published):
    errors = [row["abs_pct_error"] for row in published["detail"]]
    assert errors == sorted(errors, reverse=True)
    assert all(row["template_label"] for row in published["detail"])
    assert all(row["prediction_scope"] in ("holdout", "cross_validated")
               for row in published["detail"])


def test_detail_drops_predictions_with_no_measurement(measurements, published, tables):
    orphan = dict(published["detail"][0])
    rows = report.prediction_detail(measurements, [
        {"query_id": "not_measured", "model_version": "v1", "actual_ms": 1.0,
         "predicted_ms": 1.0, "abs_pct_error": 0.0, "in_holdout": 1}], tables)
    assert rows == []
    assert orphan["query_id"] != "not_measured"


def test_sla_verdicts_name_both_kinds_of_mistake():
    sla = 200.0
    detail = [
        {"query_id": "a", "template_id": "t1", "template_label": "slow, called",
         "actual_ms": 900.0, "predicted_ms": 800.0, "abs_pct_error": 11.0},
        {"query_id": "b", "template_id": "t2", "template_label": "slow, missed",
         "actual_ms": 900.0, "predicted_ms": 100.0, "abs_pct_error": 89.0},
        {"query_id": "c", "template_id": "t3", "template_label": "fast, false alarm",
         "actual_ms": 50.0, "predicted_ms": 500.0, "abs_pct_error": 900.0},
        {"query_id": "d", "template_id": "t4", "template_label": "fast, inside",
         "actual_ms": 50.0, "predicted_ms": 60.0, "abs_pct_error": 20.0},
    ]
    verdicts = {row["template_id"]: row["sla_verdict"] for row in report.sla_table(detail, sla)}
    assert verdicts == {"t1": "breach_called", "t2": "missed_breach",
                        "t3": "false_alarm", "t4": "inside_sla"}


def test_sla_table_aggregates_per_shape_and_sorts_worst_first(published):
    rows = report.sla_table(published["detail"])
    assert list(rows[0]) == report.SLA_COLUMNS
    assert sum(row["queries"] for row in rows) == len(published["detail"])
    worst = [row["worst_actual_ms"] for row in rows]
    assert worst == sorted(worst, reverse=True)
    assert all(row["sla_ms"] == report.SLA_MS for row in rows)


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
    broken = [dict(published["detail"][0], predicted_ms=-1.0)] + published["detail"][1:]
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
    assert "QUERY_PARAMETERIZED_HASH" in card
