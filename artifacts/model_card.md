# Query runtime model v2-5b29edef

Trained 2026-08-21T20:01:39+00:00 on 40 measured queries from 2 batch(es).

## What it predicts

Wall-clock seconds for a DuckDB query, from features that are known before the
query runs: rows in the scanned tables, estimated bytes, join count, group by,
filter selectivity, order by, window function, limit.

## Data

- 80 measured queries, median of 5 timed repetitions each after a warm-up run.
- Measured on 4 vCPU, DuckDB threads pinned to 4.
- Runtimes range 0.040s to 2.804s (median 0.172s).
- Calibration factors ranged 0.917 to 1.045. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(calibrated seconds). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 0.0947 s |
| holdout MAPE | 28.88% (95% CI 22.52–36.51) |
| holdout R2 (log10 s) | 0.8822 |
| 5-fold CV MAPE | 37.41% |
| OLS baseline MAPE | 39.09% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 seconds) |

## Permutation importance (holdout, log seconds)

| feature | importance |
|---|---|
| log_rows_after_filter | 0.4263 |
| has_groupby | 0.2250 |
| log_rows_in | 0.0798 |
| has_window | 0.0715 |
| n_joins | 0.0270 |
| selectivity | 0.0081 |
| has_orderby | 0.0070 |
| log_limit_rows | 0.0043 |
| log_bytes_est | 0.0000 |

## Calibration

| decile | queries | predicted s | actual s | error |
|---|---|---|---|---|
| 1 | 4 | 0.0517 | 0.0513 | 6.7% |
| 2 | 4 | 0.0864 | 0.0795 | 22.8% |
| 3 | 4 | 0.1161 | 0.0897 | 41.5% |
| 4 | 4 | 0.1345 | 0.1195 | 26.3% |
| 5 | 4 | 0.1711 | 0.1326 | 31.4% |
| 6 | 4 | 0.2043 | 0.2351 | 33.3% |
| 7 | 4 | 0.2689 | 0.2904 | 18.6% |
| 8 | 4 | 0.3425 | 0.4944 | 30.1% |
| 9 | 4 | 0.3987 | 0.4938 | 54.3% |
| 10 | 4 | 1.1580 | 1.3293 | 23.8% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit. It does not cover spills to disk, concurrency, or user-defined
  functions, and the model should not be trusted outside that envelope.
