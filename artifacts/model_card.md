# Query runtime model v2-97ec9ebd

Trained 2026-08-22T01:53:19+00:00 on 40 measured queries from 2 batch(es).

## What it predicts

EXECUTION_TIME in milliseconds, from the QUERY_HISTORY columns that exist at
submit time: the parsed QUERY_TEXT, WAREHOUSE_SIZE, the ROW_COUNT and BYTES of
the tables it names, and what the same QUERY_PARAMETERIZED_HASH cost before.

## Data

- 80 measured queries, median of 5 timed repetitions each after a warm-up run.
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
| holdout MAE | 149.22 ms |
| holdout MAPE | 40.35% (95% CI 28.87-52.79) |
| holdout R2 (log10 ms) | 0.7863 |
| 5-fold CV MAPE | 49.26% |
| OLS baseline MAPE | 43.38% |
| gate | FAIL (holdout MAPE <= 15% and holdout R2 >= 0.90 on log10 ms) |

## Permutation importance (holdout, log ms)

| feature | importance |
|---|---|
| log_table_rows | 0.2876 |
| predicate_literal | 0.2875 |
| warehouse_threads | 0.1461 |
| has_group_by | 0.1243 |
| has_window | 0.0482 |
| n_tables | 0.0179 |
| has_order_by | 0.0161 |
| log_limit_rows | 0.0023 |
| log_table_bytes | 0.0000 |
| n_joins | 0.0000 |
| n_predicates | 0.0000 |
| has_prior | 0.0000 |
| log_prior_ms | 0.0000 |

## Calibration

| decile | queries | predicted ms | actual ms | error |
|---|---|---|---|---|
| 1 | 4 | 70.2 | 70.4 | 33.0% |
| 2 | 4 | 102.7 | 96.3 | 14.3% |
| 3 | 4 | 162.5 | 156.2 | 60.0% |
| 4 | 4 | 204.6 | 185.7 | 20.9% |
| 5 | 4 | 270.1 | 281.9 | 23.3% |
| 6 | 4 | 330.4 | 249.5 | 76.9% |
| 7 | 4 | 366.2 | 582.4 | 50.0% |
| 8 | 4 | 438.1 | 543.3 | 33.9% |
| 9 | 4 | 652.5 | 842.6 | 57.0% |
| 10 | 4 | 1222.9 | 1365.0 | 34.2% |

## Limits

- One engine, one hardware family. A model trained on this runner predicts this
  runner; production would train on production.
- Warm caches. Every query is run once before the timed repetitions.
- The catalogue covers scans, joins to three dimensions, group by, sort, window
  and limit, on three warehouse sizes. It does not cover spills to disk,
  concurrency, or user-defined functions, and the model should not be trusted
  outside that envelope.
