# Query runtime model v1-241c4b6f

Trained 2026-08-22T00:20:30+00:00 on 28 measured queries from 1 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 40 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.044s to 2.340s (median 0.194s).
- Calibration factors ranged 1.000 to 1.037. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.1217 s |
| holdout MAPE | 32.34% (95% CI 21.36-45.31) |
| holdout R2 (log10 s) | 0.8793 |
| 5-fold CV MAPE | 73.68% |
| OLS baseline MAPE | 40.61% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4921 |
| has_groupby | 0.2387 |
| log_rows_in | 0.0991 |
| has_window | 0.0884 |
| selectivity | 0.0161 |
| log_bytes_est | 0.0000 |
| n_joins | -0.0006 |
| log_limit_rows | -0.0231 |
| has_orderby | -0.0438 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0646 | 0.0695 | 18.2% |
| 2 | 4 | 0.2540 | 0.2112 | 24.3% |
| 3 | 4 | 0.6745 | 0.5870 | 54.5% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
