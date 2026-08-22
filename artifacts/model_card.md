# Query runtime model v3-f2f82ba4

Trained 2026-08-22T00:25:35+00:00 on 80 measured queries from 3 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 120 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.040s to 2.767s (median 0.184s).
- Calibration factors ranged 0.901 to 1.037. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0331 s |
| holdout MAPE | 11.72% (95% CI 9.16-14.69) |
| holdout R2 (log10 s) | 0.9713 |
| 5-fold CV MAPE | 21.39% |
| OLS baseline MAPE | 26.37% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.6695 |
| has_groupby | 0.2869 |
| log_rows_in | 0.1448 |
| has_window | 0.1070 |
| n_joins | 0.0870 |
| log_limit_rows | 0.0165 |
| has_orderby | 0.0064 |
| log_bytes_est | 0.0000 |
| selectivity | -0.0015 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0505 | 0.0563 | 10.7% |
| 2 | 4 | 0.0690 | 0.0730 | 5.4% |
| 3 | 4 | 0.1016 | 0.1054 | 20.2% |
| 4 | 4 | 0.1252 | 0.1302 | 10.3% |
| 5 | 4 | 0.1534 | 0.1785 | 14.1% |
| 6 | 4 | 0.1837 | 0.2149 | 14.3% |
| 7 | 4 | 0.3160 | 0.3458 | 14.6% |
| 8 | 4 | 0.3985 | 0.3834 | 9.8% |
| 9 | 4 | 0.5493 | 0.5382 | 6.8% |
| 10 | 4 | 0.9961 | 0.9646 | 11.0% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
