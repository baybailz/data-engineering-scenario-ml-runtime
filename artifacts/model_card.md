# Query runtime model v4-f3d6bdea

Trained 2026-08-21T20:06:15+00:00 on 120 measured queries from 4 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 160 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.036s to 2.804s (median 0.183s).
- Calibration factors ranged 0.741 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0341 s |
| holdout MAPE | 15.86% (95% CI 12.60–19.38) |
| holdout R2 (log10 s) | 0.9525 |
| 5-fold CV MAPE | 17.45% |
| OLS baseline MAPE | 29.69% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.5395 |
| has_groupby | 0.3155 |
| has_window | 0.1220 |
| log_rows_in | 0.1084 |
| n_joins | 0.0467 |
| log_limit_rows | 0.0108 |
| has_orderby | 0.0107 |
| log_bytes_est | 0.0000 |
| selectivity | -0.0036 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0538 | 0.0463 | 17.7% |
| 2 | 4 | 0.0745 | 0.0595 | 25.9% |
| 3 | 4 | 0.0971 | 0.1018 | 15.6% |
| 4 | 4 | 0.1302 | 0.1288 | 11.9% |
| 5 | 4 | 0.1795 | 0.1947 | 13.9% |
| 6 | 4 | 0.2166 | 0.2010 | 11.2% |
| 7 | 4 | 0.2447 | 0.2116 | 16.8% |
| 8 | 4 | 0.2831 | 0.2612 | 17.9% |
| 9 | 4 | 0.4347 | 0.4738 | 7.8% |
| 10 | 4 | 0.7206 | 0.6815 | 20.0% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
