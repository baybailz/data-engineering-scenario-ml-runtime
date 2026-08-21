# Query runtime model v3-e3d9219d

Trained 2026-08-21T20:04:14+00:00 on 80 measured queries from 3 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 120 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.040s to 2.804s (median 0.182s).
- Calibration factors ranged 0.917 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0310 s |
| holdout MAPE | 11.10% (95% CI 8.53–13.91) |
| holdout R2 (log10 s) | 0.9741 |
| 5-fold CV MAPE | 21.06% |
| OLS baseline MAPE | 26.49% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.6884 |
| has_groupby | 0.2870 |
| log_rows_in | 0.1424 |
| has_window | 0.1144 |
| n_joins | 0.0896 |
| log_limit_rows | 0.0208 |
| has_orderby | 0.0036 |
| log_bytes_est | 0.0000 |
| selectivity | -0.0012 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0508 | 0.0560 | 12.6% |
| 2 | 4 | 0.0699 | 0.0728 | 3.8% |
| 3 | 4 | 0.0979 | 0.1065 | 22.9% |
| 4 | 4 | 0.1248 | 0.1313 | 9.3% |
| 5 | 4 | 0.1579 | 0.1809 | 12.7% |
| 6 | 4 | 0.1885 | 0.2103 | 9.6% |
| 7 | 4 | 0.3269 | 0.3092 | 11.2% |
| 8 | 4 | 0.4032 | 0.4207 | 11.4% |
| 9 | 4 | 0.5436 | 0.5383 | 8.1% |
| 10 | 4 | 1.0028 | 0.9568 | 9.4% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
