# Query runtime model v6-e927caf6

Trained 2026-08-21T19:52:20+00:00 on 200 measured queries from 6 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 240 measured queries, median of 8 timed repetitions each after a warm-up run.
- Measured on 28 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.013s to 1.121s (median 0.061s).
- Calibration factors ranged 0.988 to 1.337. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0119 s |
| holdout MAPE | 14.28% (95% CI 10.66–18.05) |
| holdout R2 (log10 s) | 0.9565 |
| 5-fold CV MAPE | 10.23% |
| OLS baseline MAPE | 27.34% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4977 |
| has_groupby | 0.2827 |
| log_rows_in | 0.1556 |
| has_window | 0.1480 |
| n_joins | 0.0422 |
| has_orderby | 0.0068 |
| log_limit_rows | 0.0067 |
| log_bytes_est | 0.0000 |
| selectivity | -0.0016 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0214 | 0.0199 | 8.6% |
| 2 | 4 | 0.0331 | 0.0287 | 20.1% |
| 3 | 4 | 0.0396 | 0.0361 | 13.1% |
| 4 | 4 | 0.0456 | 0.0406 | 14.0% |
| 5 | 4 | 0.0524 | 0.0447 | 18.1% |
| 6 | 4 | 0.0597 | 0.0545 | 13.2% |
| 7 | 4 | 0.0712 | 0.0616 | 15.9% |
| 8 | 4 | 0.0795 | 0.0713 | 20.0% |
| 9 | 4 | 0.1411 | 0.1377 | 5.7% |
| 10 | 4 | 0.3747 | 0.3290 | 14.1% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
