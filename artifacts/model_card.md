# Query runtime model v2-8cc5fcc0

Trained 2026-08-22T00:02:48+00:00 on 40 measured queries from 2 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 80 measured queries, median of 9 timed repetitions each after a warm-up run.
- Measured on 28 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.014s to 1.071s (median 0.063s).
- Calibration factors ranged 1.000 to 1.155. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0329 s |
| holdout MAPE | 25.34% (95% CI 19.28-31.46) |
| holdout R2 (log10 s) | 0.8845 |
| 5-fold CV MAPE | 40.95% |
| OLS baseline MAPE | 38.99% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4404 |
| has_groupby | 0.2465 |
| has_window | 0.0968 |
| log_rows_in | 0.0831 |
| n_joins | 0.0354 |
| log_limit_rows | 0.0074 |
| selectivity | 0.0058 |
| has_orderby | 0.0001 |
| log_bytes_est | 0.0000 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0183 | 0.0200 | 8.1% |
| 2 | 4 | 0.0284 | 0.0313 | 21.2% |
| 3 | 4 | 0.0366 | 0.0319 | 25.6% |
| 4 | 4 | 0.0473 | 0.0502 | 14.1% |
| 5 | 4 | 0.0615 | 0.0449 | 37.2% |
| 6 | 4 | 0.0767 | 0.0770 | 24.5% |
| 7 | 4 | 0.0952 | 0.1219 | 18.1% |
| 8 | 4 | 0.1231 | 0.1729 | 47.4% |
| 9 | 4 | 0.1708 | 0.2164 | 34.5% |
| 10 | 4 | 0.4670 | 0.5088 | 22.7% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
