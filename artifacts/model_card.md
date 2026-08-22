# Query runtime model v3-c193ca11

Trained 2026-08-22T01:38:12+00:00 on 80 measured queries from 3 batch(es).

## What it predicts

EXECUTION_TIME in milliseconds, from the QUERY_HISTORY columns that exist at
submit time: the parsed QUERY_TEXT, WAREHOUSE_SIZE, the ROW_COUNT and BYTES of
the tables it names, and what the same QUERY_PARAMETERIZED_HASH cost before.

## Data

- 120 measured queries, median of 6 timed repetitions each after a warm-up run.
- Engine duckdb-1.3.2, warehouse sizes X-Small, Small, Medium applied as thread counts.
- Runtimes range 15.7 ms to 2132.5 ms (median 110.0 ms).
- Calibration factors ranged 0.986 to 1.252. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(EXECUTION_TIME in ms, runner drift divided out). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 37.10 ms |
| holdout MAPE | 17.17% (95% CI 13.45-21.12) |
| holdout R2 (log10 ms) | 0.9680 |
| 5-fold CV MAPE | 29.19% |
| OLS baseline MAPE | 51.76% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 ms) |

## Permutation importance (holdout, log ms)

| feature | importance |
|---|---|
| predicate_literal | 0.5342 |
| log_table_rows | 0.3998 |
| warehouse_threads | 0.3449 |
| has_group_by | 0.3344 |
| has_window | 0.1019 |
| n_tables | 0.0691 |
| log_limit_rows | 0.0096 |
| has_order_by | 0.0030 |
| log_table_bytes | 0.0000 |
| n_joins | 0.0000 |
| n_predicates | 0.0000 |
| log_prior_ms | -0.0019 |
| has_prior | -0.0035 |

## Calibration

| decile | queries | predicted ms | actual ms | error |
|---|---|---|---|---|
| 1 | 4 | 21.7 | 22.0 | 8.2% |
| 2 | 4 | 39.3 | 42.2 | 26.8% |
| 3 | 4 | 54.4 | 46.9 | 19.6% |
| 4 | 4 | 70.9 | 77.7 | 13.8% |
| 5 | 4 | 105.1 | 103.5 | 17.0% |
| 6 | 4 | 146.0 | 125.7 | 16.8% |
| 7 | 4 | 215.9 | 206.2 | 13.4% |
| 8 | 4 | 313.1 | 295.6 | 21.8% |
| 9 | 4 | 476.9 | 573.1 | 16.4% |
| 10 | 4 | 788.6 | 672.0 | 17.9% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit, on three warehouse sizes. It does not cover spills to disk,
  concurrency, or user-defined functions, and the model should not be trusted
  outside that envelope.
