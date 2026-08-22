# Query runtime model v3-019f7483

Trained 2026-08-22T01:56:51+00:00 on 80 measured queries from 3 batch(es).

## What it predicts

EXECUTION_TIME in milliseconds, from the QUERY_HISTORY columns that exist at
submit time: the parsed QUERY_TEXT, WAREHOUSE_SIZE, the ROW_COUNT and BYTES of
the tables it names, and what the same QUERY_PARAMETERIZED_HASH cost before.

## Data

- 120 measured queries, median of 5 timed repetitions each after a warm-up run.
- Engine duckdb-1.3.2, warehouse sizes X-Small, Small, Medium applied as thread counts.
- Runtimes range 45.0 ms to 3147.2 ms (median 258.4 ms).
- Calibration factors ranged 1.000 to 1.056. The calibration query is re-timed every ten queries and every reading is divided by the value interpolated to its position.

## Method

- Target: log(EXECUTION_TIME in ms, runner drift divided out). Model: HistGradientBoostingRegressor.
- Baseline: ordinary least squares on the same features.
- Holdout: the most recent batch, never used for fitting.
- Published predictions are out of sample (holdout model, or 5-fold cross-validated for earlier batches).

## Results

| metric | value |
|---|---|
| holdout MAE | 44.78 ms |
| holdout MAPE | 12.35% (95% CI 9.42-15.68) |
| holdout R2 (log10 ms) | 0.9752 |
| 5-fold CV MAPE | 27.79% |
| OLS baseline MAPE | 49.22% |
| gate | PASS (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 ms) |

## Permutation importance (holdout, log ms)

| feature | importance |
|---|---|
| predicate_literal | 0.5272 |
| log_table_rows | 0.3965 |
| has_group_by | 0.2574 |
| warehouse_threads | 0.2146 |
| has_window | 0.0782 |
| n_tables | 0.0542 |
| has_order_by | 0.0192 |
| log_prior_ms | 0.0113 |
| log_limit_rows | 0.0070 |
| has_prior | 0.0052 |
| log_table_bytes | 0.0000 |
| n_joins | 0.0000 |
| n_predicates | 0.0000 |

## Calibration

| decile | queries | predicted ms | actual ms | error |
|---|---|---|---|---|
| 1 | 4 | 61.1 | 59.0 | 6.0% |
| 2 | 4 | 96.8 | 81.9 | 24.9% |
| 3 | 4 | 135.0 | 155.5 | 12.7% |
| 4 | 4 | 168.7 | 166.5 | 12.3% |
| 5 | 4 | 249.7 | 226.1 | 11.2% |
| 6 | 4 | 308.1 | 333.0 | 9.5% |
| 7 | 4 | 400.2 | 403.6 | 13.2% |
| 8 | 4 | 598.8 | 551.7 | 18.8% |
| 9 | 4 | 916.2 | 956.5 | 6.5% |
| 10 | 4 | 1248.8 | 1204.5 | 8.5% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit, on three warehouse sizes. It does not cover spills to disk,
  concurrency, or user-defined functions, and the model should not be trusted
  outside that envelope.
