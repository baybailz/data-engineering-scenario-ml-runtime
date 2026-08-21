# Query runtime model v5-d0ae27ac

Trained 2026-08-21T20:08:41+00:00 on 160 measured queries from 5 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 200 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.036s to 2.804s (median 0.187s).
- Calibration factors ranged 0.741 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0452 s |
| holdout MAPE | 9.37% (95% CI 7.00–11.95) |
| holdout R2 (log10 s) | 0.9810 |
| 5-fold CV MAPE | 13.26% |
| OLS baseline MAPE | 25.69% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.6376 |
| has_groupby | 0.3229 |
| log_rows_in | 0.1604 |
| has_window | 0.1363 |
| n_joins | 0.1097 |
| log_limit_rows | 0.0189 |
| has_orderby | 0.0027 |
| log_bytes_est | 0.0000 |
| selectivity | -0.0029 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0606 | 0.0647 | 5.9% |
| 2 | 4 | 0.0718 | 0.0749 | 6.9% |
| 3 | 4 | 0.0928 | 0.0983 | 7.3% |
| 4 | 4 | 0.1249 | 0.1384 | 11.3% |
| 5 | 4 | 0.1670 | 0.1778 | 5.9% |
| 6 | 4 | 0.1912 | 0.2108 | 8.9% |
| 7 | 4 | 0.2315 | 0.2266 | 8.0% |
| 8 | 4 | 0.4635 | 0.4602 | 14.4% |
| 9 | 4 | 0.7402 | 0.8030 | 14.6% |
| 10 | 4 | 1.2690 | 1.4088 | 10.4% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
