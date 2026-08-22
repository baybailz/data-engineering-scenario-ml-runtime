# Query runtime model v2-df244983

Trained 2026-08-22T00:23:03+00:00 on 40 measured queries from 2 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 80 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.040s to 2.767s (median 0.172s).
- Calibration factors ranged 0.901 to 1.037. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.1005 s |
| holdout MAPE | 30.89% (95% CI 23.97-38.76) |
| holdout R2 (log10 s) | 0.8669 |
| 5-fold CV MAPE | 34.97% |
| OLS baseline MAPE | 39.66% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4022 |
| has_groupby | 0.2288 |
| log_rows_in | 0.0737 |
| has_window | 0.0710 |
| n_joins | 0.0220 |
| selectivity | 0.0060 |
| has_orderby | 0.0011 |
| log_limit_rows | 0.0011 |
| log_bytes_est | 0.0000 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0527 | 0.0510 | 10.3% |
| 2 | 4 | 0.0829 | 0.0781 | 21.9% |
| 3 | 4 | 0.1141 | 0.0829 | 47.9% |
| 4 | 4 | 0.1389 | 0.1269 | 19.2% |
| 5 | 4 | 0.1827 | 0.1268 | 45.7% |
| 6 | 4 | 0.2088 | 0.2471 | 31.4% |
| 7 | 4 | 0.2745 | 0.2817 | 17.2% |
| 8 | 4 | 0.3343 | 0.5139 | 33.5% |
| 9 | 4 | 0.3961 | 0.4725 | 57.0% |
| 10 | 4 | 1.1149 | 1.3268 | 24.7% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
