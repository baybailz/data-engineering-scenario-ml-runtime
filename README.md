# Predict how long a query will run before it runs.

Warehouse work is queued, sized and priced on a guess. This pipeline measures real
queries on the runner and trains a model on features known before the query starts:
table sizes, joins, group by, filter selectivity, sort, window, limit. It publishes the
error with a confidence interval and a pass/fail gate. Nothing here is simulated.

**[Live demo →](https://baybailz.github.io/data-engineering-scenario-ml-runtime/)**

## The hard part

Not the model. The model is 40 lines of scikit-learn and the signal is physics.

- **Measuring anything under a second on a shared runner.** A query that takes 20 ms is
  mostly scheduler noise. Every query is warmed once, then repeated until 0.6 s of timed
  work has accumulated, and the median is taken.
- **Drift between batches.** A batch measured while the runner was busy looks like a batch
  of slower queries, and a time-ordered holdout reads that as model error. The same
  calibration query is re-timed every ten queries, and each reading is divided by the
  calibration value interpolated to its position.
- **Saying how wrong it is.** Holdout MAPE alone is a number without a spread. The
  pipeline reports a bootstrap 95% CI, R², an OLS baseline to beat, permutation
  importances and a calibration table, and it publishes a model that misses the gate with
  the gate marked FAIL.
- **Keeping predictions out of sample.** Holdout queries are scored by a model that never
  saw them; earlier queries by 5-fold cross-validation. Nothing on the page is a model
  grading its own training data.

## How it works

1. `scripts/make_workload.py` builds four fact tables (2M–8M rows), three dimensions and a
   catalogue of 60 query shapes × 4 filter selectivities, split into six batches of 40.
   Deterministic: tables are generated from row numbers through `hash()`.
2. `scripts/run.py --action measure_batch` times the next batch on DuckDB with threads
   pinned to 4, records the pre-run features and the calibrated runtime, and rebuilds the
   landing seed from `state/`.
3. `scripts/train.py` fits a `HistGradientBoostingRegressor` on log(seconds) plus an OLS
   baseline, scores them on the most recent batch, and writes `artifacts/model.pkl`,
   `model_card.md`, `metrics.json` and one prediction row per measured query.
4. `dbt build` runs stage → transform → conformed (`dim_query_template`, `fact_query_run`,
   `fact_query_prediction`, `dim_model_version`) → datamart (`dm_runtime_sla`,
   `dm_prediction_detail`, `dm_model_scorecard`), with 73 models and tests.
5. `scripts/export_json.py` publishes `docs/data/*.json` and the workflow commits it back,
   so the page renders what the pipeline actually produced.

## Layout

```
docs/index.html          the shell: presentation deck + demo console
docs/slides.js           the slides, including the scatter and the learning curve
docs/panels.js           the console tabs
docs/scenario.json       title, repo, pipeline steps, which tables to export
incoming/batch_*.csv     the query catalogue: 240 queries with their features
scripts/make_workload.py builds workload.duckdb and the catalogue
scripts/run.py           measures the next batch -> query_run_landing seed
scripts/train.py         trains, scores, gates, writes artifacts/ and two seeds
scripts/export_json.py   publishes docs/data/*.json
scripts/scenario.py      headline numbers + the log row for a run
models/                  stage -> transform -> conformed -> datamart
tests/                   every run has a prediction; no prediction is negative
artifacts/               model.pkl, model_card.md, metrics.json, predictions.csv
.github/workflows/pipeline.yml   measure -> train -> dbt build -> export -> commit
.github/workflows/ci.yml         PR gate: sqlfluff + dbt build + a short measure/train
```

Locally:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export DBT_PROFILES_DIR=.
.venv/bin/python scripts/run.py --action reset && .venv/bin/dbt build --full-refresh
.venv/bin/python scripts/run.py --action measure_batch && .venv/bin/python scripts/train.py
.venv/bin/dbt build --select tag:scenario && .venv/bin/python scripts/export_json.py --action measure_batch
(cd docs && python -m http.server 8000)
```

Conventions: [CONVENTIONS.md](CONVENTIONS.md).
