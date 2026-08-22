# Predict how long a query will run before it runs.

Teams size machines, set timeouts and price jobs on a guess. This is a standalone
solution that stops guessing: it times real queries on the machine it runs on, trains a
model on features known before a query starts — table sizes, joins, group by, filter
selectivity, sort, window, limit — and publishes the error with a confidence interval and
a pass/fail gate. No warehouse, no orchestrator, no notebook. Nothing here is simulated.

**[Live demo →](https://baybailz.github.io/data-engineering-scenario-ml-runtime/)** — a
presentation and a working console. The Run button dispatches a GitHub Actions workflow
that measures the next batch, retrains, and publishes the result back to the page. The
published model also runs in your browser: set a query shape and it scores it.

## The hard part

Not the model. The model is 40 lines of scikit-learn and the signal is physics.

- **Measuring anything under a second.** A query that takes 20 ms is mostly scheduler
  noise. Every query is warmed once, then repeated until 0.6 s of timed work has
  accumulated, and the median is taken.
- **Drift between batches.** A batch measured while the machine was busy looks like a
  batch of slower queries, and a time-ordered holdout reads that as model error. The same
  calibration query is re-timed every ten queries, and each reading is divided by the
  calibration value interpolated to its position.
- **Saying how wrong it is.** A MAPE alone is a number without a spread. Every run reports
  a bootstrap 95% CI, R², an OLS baseline to beat, permutation importances and a
  calibration table — and publishes a model that misses the gate with the gate marked
  FAIL.
- **Keeping predictions out of sample.** Holdout queries are scored by a model that never
  saw them; earlier queries by 5-fold cross-validation. Nothing on the page is a model
  grading its own training data.

## How it works

1. **Measure.** `workload.py` builds four fact tables (2M–8M rows), three dimensions and a
   catalogue of 60 query shapes × 4 filter selectivities, split into six batches of 40.
   `measure.py` times the next batch on DuckDB with threads pinned to 4, recording the
   pre-run features and the calibrated runtime.
2. **Train.** `train.py` fits a `HistGradientBoostingRegressor` on log(seconds) plus an OLS
   baseline, scores them on the most recent batch, gates the result against a rule fixed in
   advance, and writes `artifacts/model.pkl` and `model_card.md`. It exports the deployed
   model to `docs/data/model.onnx`, checked against scikit-learn to 1e-4 before it is
   written, so the page can score a query in the visitor's browser.
3. **Predict.** `predict.py` scores query shapes the model has never seen — including the
   next batch in the queue, which arrives on the page with a predicted runtime attached
   before anything runs.
4. **Publish.** `report.py` writes `data/*.csv`: every prediction with its shape, one row
   per model version, and one row per query shape against the SLA. The run then checks what
   it wrote — every measured query scored, no negative predictions, every prediction out of
   sample — and fails if a check fails.
5. `scripts/export_json.py` turns those CSVs into `docs/data/*.json` and the workflow
   commits everything back, so the page renders what the run actually produced.

## Results

Measured on the GitHub Actions runner. Current numbers are on the live page and in
[`artifacts/model_card.md`](artifacts/model_card.md), which is rewritten on every run:
holdout MAPE with a bootstrap 95% CI, R² on log10 seconds, MAE, the OLS baseline it has to
beat, permutation importance and a calibration table by decile. The gate is
`holdout MAPE <= 15% and holdout R2 >= 0.90`, fixed before any of it was known.

## Layout

```
src/runtime_model/workload.py   builds the tables and the query catalogue
src/runtime_model/measure.py    times a batch, divides out machine drift
src/runtime_model/features.py   the feature vector, one definition
src/runtime_model/train.py      fit, score, gate, export to ONNX
src/runtime_model/predict.py    score a query shape that has not been run
src/runtime_model/report.py     the published tables and the model card
scripts/run.py                  one batch end to end: measure -> train -> publish
scripts/export_json.py          data/*.csv -> docs/data/*.json for the page
tests/                          pytest: features, calibration, gate, ONNX parity,
                                report tables, and one real end-to-end smoke test
data/                           measurements, predictions, model versions, SLA
artifacts/                      model.pkl, model_card.md, metrics.json
incoming/batch_*.csv            the queue: 240 queries with their features
state/                          what has been measured; every table rebuilds from it
docs/index.html                 the shell: presentation deck + demo console
docs/slides.js                  the slides, the scatter, the learning curve, try-it
docs/panels.js                  the console tabs
docs/data/model.onnx            the published model, run in the browser
.github/workflows/pipeline.yml  measure -> train -> publish -> export -> commit
.github/workflows/ci.yml        PR gate: ruff + pytest
```

Locally:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest
.venv/bin/python scripts/run.py --action reset
.venv/bin/python scripts/run.py --action measure_batch
.venv/bin/python scripts/export_json.py --action measure_batch
(cd docs && python -m http.server 8000)
```

`workload.duckdb` is not committed: it is large, and `workload.py` rebuilds it in seconds
from row numbers through `hash()`, so it is byte-identical on any machine. The catalogue
CSVs are committed, so the queue a visitor sees is exactly the queue the runner measures.
