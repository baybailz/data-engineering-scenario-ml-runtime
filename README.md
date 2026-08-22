# Predict how long a query will run before it runs.

Teams size warehouses, set timeouts and price jobs on a guess. This is a standalone
solution that stops guessing. It times real queries on the machine it runs on and writes
each one as a row in the exact column layout of
`SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, with `ACCOUNT_USAGE.TABLES` beside it. The model
trains on the columns that exist when the statement is submitted — the parsed SQL text,
the warehouse size, the size of the tables it names — and publishes the error with a
confidence interval and a pass/fail gate. Nothing here is simulated.

**[Live demo →](https://baybailz.github.io/data-engineering-scenario-ml-runtime/)** — a
presentation and a working console. The Run button dispatches a GitHub Actions workflow
that measures the next batch, retrains, and publishes the result back to the page. The
published model also runs in your browser: write a query shape and it scores it.

## The hard part

Not the model. The model is 40 lines of scikit-learn and the signal is physics.

- **Only using what you would have.** `BYTES_SCANNED`, `PARTITIONS_SCANNED` and
  `ROWS_PRODUCED` predict runtime beautifully and are worthless: the engine writes them
  once the query is over. `features.featurise` projects every row down to `QUERY_TEXT`
  and `WAREHOUSE_SIZE` before it builds anything, so the after-the-fact columns are not
  merely unused — they are not in the dictionary the feature builder can see. A test
  blanks all 45 of them and asserts not one feature moves.
- **Filling a warehouse's table honestly.** 75 columns, and a local engine can speak to
  34 of them. The rest are NULL rather than a plausible number, and
  [`docs/data_dictionary.md`](docs/data_dictionary.md) says of every column whether it is
  measured, derived, estimated or null.
- **Measuring anything under a second.** A query that takes 20 ms is mostly scheduler
  noise. Every query is warmed once, then repeated until 0.6 s of timed work has
  accumulated, and the median is taken.
- **Drift between batches.** A batch measured while the machine was busy looks like a
  batch of slower queries, and a time-ordered holdout reads that as model error. The same
  calibration query is re-timed every ten queries, and each reading is divided by the
  calibration value interpolated to its position. Snowflake has no column for how busy
  the machine was, so that factor is published in `data/calibration.csv` rather than
  smuggled into `QUERY_HISTORY`.
- **Saying how wrong it is.** Every run reports a bootstrap 95% CI, R², an OLS baseline to
  beat, permutation importances and a calibration table — and publishes a model that
  misses the gate with the gate marked FAIL.

## How it works

1. **Measure.** `workload.py` builds four fact tables (2M–8M rows), three dimensions and a
   catalogue of 60 query shapes × 4 filter constants, each assigned a warehouse size,
   split into six batches of 40. `measure.py` sets `WAREHOUSE_SIZE` on the engine as 1, 2
   or 4 threads, times the batch on DuckDB, and writes QUERY_HISTORY rows: real SQL, real
   start and end times, measured `EXECUTION_TIME` and `COMPILATION_TIME`, exact
   `ROWS_PRODUCED`.
2. **Parse.** `parse.py` asks eight structural questions of `QUERY_TEXT` — tables named,
   joins, group by, order by, window, limit, predicates and the constant each compares
   against — and looks the table sizes up in `data/tables.csv`. That, plus the warehouse
   size and what the same `QUERY_PARAMETERIZED_HASH` cost in earlier batches, is the whole
   feature vector.
3. **Train.** `train.py` fits a `HistGradientBoostingRegressor` on log(ms) plus an OLS
   baseline, scores them on the most recent batch, gates the result against a rule fixed in
   advance, and writes `artifacts/model.pkl` and `model_card.md`. It exports the deployed
   model to `docs/data/model.onnx`, checked against scikit-learn to 1e-4 before it is
   written, so the page can score a query in the visitor's browser.
4. **Predict.** `predict.py` scores query shapes the model has never seen — including the
   next batch in the queue, which arrives on the page with a predicted runtime attached
   before anything runs.
5. **Publish.** `report.py` writes `data/*.csv` and `scripts/export_json.py` turns them into
   `docs/data/*.json`. The run then checks what it wrote — every measured query scored, no
   negative predictions, every prediction out of sample — and fails if a check fails.

## Results

See the live demo for the current numbers: every figure below is regenerated on each run
into [`artifacts/model_card.md`](artifacts/model_card.md), which also carries the
permutation importances, the calibration table by decile and the model's limits. Holdout
is the most recent batch, never used for fitting; earlier batches are scored by 5-fold
cross-validation. The gate — `holdout MAPE <= 15% and holdout R2 >= 0.90` — was fixed
before the first number was known and is not moved to fit a result.

Restricting the features to the pre-run columns costs accuracy, and that is the point: an
earlier version of this repository reached 11.7% MAPE using a filter selectivity that a
planner does not have. What is published now is what the same method would get against a
real `ACCOUNT_USAGE` export.

## Layout

```
src/runtime_model/snowflake.py  the ACCOUNT_USAGE column layout, and which half is pre-run
src/runtime_model/workload.py   builds the tables, the catalogue table and the query queue
src/runtime_model/parse.py      reads a query's shape out of QUERY_TEXT
src/runtime_model/measure.py    times a batch, writes QUERY_HISTORY rows
src/runtime_model/features.py   the feature vector, and the projection that guards it
src/runtime_model/train.py      fit, score, gate, export to ONNX
src/runtime_model/predict.py    score a statement that has not been run
src/runtime_model/report.py     the published tables and the model card
scripts/run.py                  one batch end to end: measure -> train -> publish
scripts/export_json.py          data/*.csv -> docs/data/*.json for the page
tests/                          pytest: parsing, the leakage guard, the CSV schema,
                                calibration, the gate, ONNX parity, and one real
                                end-to-end smoke test
data/query_history.csv          the input, in ACCOUNT_USAGE.QUERY_HISTORY's shape
data/tables.csv                 the catalogue, in ACCOUNT_USAGE.TABLES' shape
data/calibration.csv            the runner drift, which has no Snowflake column
docs/data_dictionary.md         every column: meaning, and measured / derived / null
incoming/batch_*.csv            the queue: 240 statements and the warehouse to run them on
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
