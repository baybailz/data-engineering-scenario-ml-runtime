# Query runtime model v1-e348fc0a

Trained 2026-08-21T19:58:52+00:00 on 28 measured queries from 1 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 40 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.043s to 2.332s (median 0.190s).
- Calibration factors ranged 1.000 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.1152 s |
| holdout MAPE | 32.47% (95% CI 21.92–44.44) |
| holdout R2 (log10 s) | 0.8853 |
| 5-fold CV MAPE | 73.44% |
| OLS baseline MAPE | 40.67% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4902 |
| has_groupby | 0.2382 |
| log_rows_in | 0.0935 |
| has_window | 0.0879 |
| selectivity | 0.0299 |
| log_bytes_est | 0.0000 |
| n_joins | -0.0046 |
| log_limit_rows | -0.0243 |
| has_orderby | -0.0381 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0634 | 0.0678 | 20.8% |
| 2 | 4 | 0.2543 | 0.2079 | 25.6% |
| 3 | 4 | 0.6606 | 0.5829 | 51.1% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
