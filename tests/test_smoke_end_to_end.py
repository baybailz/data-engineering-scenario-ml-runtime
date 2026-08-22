"""The whole solution, for real, on a short batch.

Everything else in this suite runs on synthetic rows. This one builds the
workload, times real queries on DuckDB, trains, publishes and exports, by
running the two entry points exactly as the pipeline runs them -- in a copy of
the project, so the committed state is untouched.

Fourteen queries rather than forty: enough to train on, quick enough to sit in
CI on every pull request.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUERIES = 14


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    """A working copy: the code, two batches of the catalogue, the config."""
    home = tmp_path_factory.mktemp("project")
    shutil.copytree(ROOT / "src", home / "src")
    shutil.copytree(ROOT / "scripts", home / "scripts")
    (home / "incoming").mkdir()
    for name in ("batch_01.csv", "batch_02.csv"):
        shutil.copy(ROOT / "incoming" / name, home / "incoming" / name)
    (home / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "scenario.json", home / "docs" / "scenario.json")
    return home


def run(project: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, *args], cwd=project, check=True,
                            capture_output=True, text=True, timeout=900)
    return result.stdout


def read_csv_rows(path: Path) -> list[dict]:
    import csv
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def measured(project: Path) -> Path:
    run(project, "scripts/run.py", "--action", "reset")
    output = run(project, "scripts/run.py", "--action", "measure_batch",
                 "--limit", str(QUERIES))
    assert "[measure]" in output and "[train]" in output
    assert "[check] FAIL" not in output
    run(project, "scripts/export_json.py", "--action", "measure_batch")
    return project


def test_reset_leaves_no_model_and_empty_tables(project: Path):
    run(project, "scripts/run.py", "--action", "reset")
    assert json.loads((project / "state" / "loaded_files.json").read_text()) == []
    assert read_csv_rows(project / "data" / "measurements.csv") == []
    assert not (project / "docs" / "data" / "model.onnx").exists()


def test_a_batch_is_measured_trained_and_published(measured: Path):
    measurements = read_csv_rows(measured / "data" / "measurements.csv")
    predictions = read_csv_rows(measured / "data" / "predictions.csv")
    versions = read_csv_rows(measured / "data" / "model_versions.csv")
    sla = read_csv_rows(measured / "data" / "sla.csv")

    assert len(measurements) == QUERIES
    assert len(predictions) == QUERIES
    assert len(versions) == 1
    assert sla
    assert all(float(row["median_seconds"]) > 0 for row in measurements)
    assert all(int(row["reps"]) >= 5 for row in measurements)
    assert all(float(row["predicted_seconds"]) > 0 for row in predictions)
    assert versions[0]["gate_status"] in ("pass", "fail")


def test_the_model_and_its_card_are_written(measured: Path):
    assert (measured / "artifacts" / "model.pkl").stat().st_size > 0
    assert "# Query runtime model" in (measured / "artifacts" / "model_card.md").read_text()
    meta = json.loads((measured / "docs" / "data" / "model_meta.json").read_text())
    assert meta["onnx_vs_sklearn_max_diff"] < 1e-4
    assert (measured / "docs" / "data" / "model.onnx").stat().st_size == meta["onnx_bytes"]


def test_the_page_json_is_complete(measured: Path):
    out = measured / "docs" / "data"
    summary = json.loads((out / "summary.json").read_text())
    tables = json.loads((out / "tables.json").read_text())
    logs = json.loads((out / "logs.json").read_text())
    models = json.loads((out / "models.json").read_text())

    assert summary["queries_measured"] == QUERIES
    assert summary["checks_failed"] == 0 and summary["checks_passed"] > 0
    assert summary["model_version"] and summary["model_card"]
    assert summary["holdout_mape_pct"] > 0
    assert set(tables) == {"predictions", "model_versions", "sla"}
    assert logs["history"][-1]["measure"].startswith("batch_01")
    assert "PASS=" in logs["history"][-1]["publish"]
    assert any(f["path"] == "src/runtime_model/train.py" for f in models["files"])


def test_the_queue_is_scored_before_it_is_measured(measured: Path):
    """The next batch arrives with a prediction attached. That is the product."""
    queued = json.loads((measured / "docs" / "data" / "next_file.json").read_text())
    assert queued["name"] == "batch_02"
    assert queued["rows"]
    assert all(row["predicted_seconds"] > 0 for row in queued["rows"])
    assert {row["predicted_by"] for row in queued["rows"]} == {
        json.loads((measured / "docs" / "data" / "summary.json").read_text())["model_version"]}


def test_the_queue_accumulates_then_stops(measured: Path):
    """Published tables are rebuilt from state, so an extra run cannot duplicate."""
    before = read_csv_rows(measured / "data" / "measurements.csv")
    run(measured, "scripts/run.py", "--action", "measure_batch", "--limit", str(QUERIES))
    after = read_csv_rows(measured / "data" / "measurements.csv")
    assert len(after) == 2 * len(before)
    assert {row["batch_name"] for row in after} == {"batch_01", "batch_02"}

    output = run(measured, "scripts/run.py", "--action", "measure_batch")
    assert "every batch has been measured" in output
    again = read_csv_rows(measured / "data" / "measurements.csv")
    assert len(again) == len(after)
    assert len({row["query_id"] for row in again}) == len(again)
