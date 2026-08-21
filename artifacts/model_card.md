# Query runtime model v7-00b9305f

Trained 2026-08-21T21:54:43+00:00 on 200 measured queries from 6 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 240 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.036s to 2.804s (median 0.180s).
- Calibration factors ranged 0.741 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0285 s |
| holdout MAPE | 10.86% (95% CI 8.30–13.95) |
| holdout R2 (log10 s) | 0.9651 |
| 5-fold CV MAPE | 11.65% |
| OLS baseline MAPE | 23.00% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.5153 |
| has_groupby | 0.2369 |
| log_rows_in | 0.1636 |
| has_window | 0.1252 |
| n_joins | 0.0317 |
| has_orderby | 0.0086 |
| log_bytes_est | 0.0000 |
| log_limit_rows | -0.0003 |
| selectivity | -0.0006 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0572 | 0.0610 | 8.0% |
| 2 | 4 | 0.0864 | 0.0878 | 7.7% |
| 3 | 4 | 0.1160 | 0.1118 | 6.9% |
| 4 | 4 | 0.1292 | 0.1140 | 13.5% |
| 5 | 4 | 0.1454 | 0.1399 | 19.1% |
| 6 | 4 | 0.1610 | 0.1699 | 12.2% |
| 7 | 4 | 0.1860 | 0.1829 | 10.5% |
| 8 | 4 | 0.2146 | 0.1963 | 12.1% |
| 9 | 4 | 0.3758 | 0.3617 | 4.3% |
| 10 | 4 | 0.9079 | 0.7918 | 14.2% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
