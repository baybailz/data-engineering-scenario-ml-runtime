# Query runtime model v1-ece1c0d7

Trained 2026-08-22T01:50:12+00:00 on 28 measured queries from 1 batch(es).

## What it predicts

EXECUTION_TIME in milliseconds, from the QUERY_HISTORY columns that exist at
submit time: the parsed QUERY_TEXT, WAREHOUSE_SIZE, the ROW_COUNT and BYTES of
the tables it names, and what the same QUERY_PARAMETERIZED_HASH cost before.

## Data

- 40 measured queries, median of 5 timed repetitions each after a warm-up run.
- Engine duckdb-1.3.2, warehouse sizes X-Small, Small, Medium applied as thread counts.
- Runtimes range 55.0 ms to 3147.2 ms (median 277.9 ms).
- Calibration factors ranged 1.000 to 1.026. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(EXECUTION_TIME in ms, runner drift divided out). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 118.05 ms |
| holdout MAPE | 24.69% (95% CI 16.00-32.82) |
| holdout R2 (log10 ms) | 0.8972 |
| 5-fold CV MAPE | 65.49% |
| OLS baseline MAPE | 31.01% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 ms) |

## Permutation importance (holdout, log ms)

| feature | importance |
|---|---|
| log_table_rows | 0.3075 |
| predicate_literal | 0.3005 |
| has_group_by | 0.1726 |
| warehouse_threads | 0.0716 |
| n_tables | 0.0359 |
| has_order_by | 0.0322 |
| has_window | 0.0148 |
| log_table_bytes | 0.0000 |
| n_joins | 0.0000 |
| n_predicates | 0.0000 |
| has_prior | 0.0000 |
| log_prior_ms | 0.0000 |
| log_limit_rows | -0.0019 |

## Calibration

| decile | queries | predicted ms | actual ms | error |
|---|---|---|---|---|
| 1 | 4 | 97.1 | 116.1 | 15.9% |
| 2 | 4 | 372.5 | 318.6 | 29.8% |
| 3 | 4 | 673.0 | 810.4 | 28.3% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit, on three warehouse sizes. It does not cover spills to disk,
  concurrency, or user-defined functions, and the model should not be trusted
  outside that envelope.
