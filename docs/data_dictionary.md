# Data dictionary

The input to this model is written in the exact column layout of
`SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` and `SNOWFLAKE.ACCOUNT_USAGE.TABLES`, so
`data/query_history.csv` can be put beside a real `ACCOUNT_USAGE` export and read
the same way. The measurements underneath are real DuckDB timings taken on the
machine that ran the pipeline.

Every column carries one of four labels.

| label | means |
|---|---|
| **measured** | a number this run produced by timing or counting something |
| **derived** | computed from a measurement, or a constant we set ourselves and know to be true |
| **estimated** | our best figure for something the engine does not report. Named as an estimate wherever it appears |
| **null** | does not apply to a local engine. Left empty rather than filled with a plausible number |

Nothing is filled with a plausible number. A column DuckDB has nothing to say
about is NULL, and there are 41 of them.

## data/query_history.csv

The statement recorded in `QUERY_TEXT` is the SELECT. The runner executes it as
`CREATE OR REPLACE TEMP TABLE q_result AS <query>`, so the whole result is
materialised and a LIMIT is honoured — which is also why `ROWS_PRODUCED` is
exact rather than an estimate.

### Identity and session

| column | label | meaning |
|---|---|---|
| `QUERY_ID` | derived | UUID assigned when the statement is submitted |
| `QUERY_TEXT` | measured | the exact SQL that ran |
| `DATABASE_NAME` | derived | `ANALYTICS` |
| `SCHEMA_NAME` | derived | `PUBLIC` |
| `QUERY_TYPE` | derived | `SELECT`. Every query in the catalogue is one |
| `SESSION_ID` | derived | one session per batch |
| `USER_NAME` | derived | `BAILEY` |
| `ROLE_NAME` | derived | `ANALYST` |
| `ROLE_TYPE` | derived | `ROLE` |
| `USER_TYPE` | derived | `PERSON` |
| `USER_DATABASE_NAME` | derived | the user's default database |
| `USER_SCHEMA_NAME` | derived | the user's default schema |
| `SECONDARY_ROLE_STATS` | derived | `NONE`; no secondary roles are used |
| `IS_CLIENT_GENERATED_STATEMENT` | derived | `FALSE`; every statement comes from the catalogue |
| `RELEASE_VERSION` | derived | the engine version that ran it, e.g. `duckdb-1.3.2` |
| `TRANSACTION_ID` | null | autocommit, no explicit transaction |

### Warehouse

| column | label | meaning |
|---|---|---|
| `WAREHOUSE_NAME` | derived | `COMPUTE_WH` |
| `WAREHOUSE_SIZE` | measured | `X-Small`, `Small` or `Medium`, applied as 1, 2 or 4 engine threads before the query is timed |
| `WAREHOUSE_TYPE` | derived | `STANDARD` |
| `CLUSTER_NUMBER` | derived | `1`; single cluster |
| `QUERY_TAG` | derived | the batch the query was measured in, e.g. `batch_03` |

### Outcome and timing

| column | label | meaning |
|---|---|---|
| `EXECUTION_STATUS` | measured | `SUCCESS`. A failing query fails the run |
| `ERROR_CODE` | null | nothing failed |
| `ERROR_MESSAGE` | null | nothing failed |
| `START_TIME` | measured | wall clock immediately before the timed repetitions |
| `END_TIME` | derived | `START_TIME` + compilation + execution |
| `TOTAL_ELAPSED_TIME` | derived | compilation + execution, ms. There is no queue to add |
| `COMPILATION_TIME` | measured | median of three `EXPLAIN` timings, ms: parse, bind and optimise without executing |
| `EXECUTION_TIME` | measured | median of the timed repetitions, ms. **This is the target** |
| `QUEUED_PROVISIONING_TIME` | null | the warehouse is always up |
| `QUEUED_REPAIR_TIME` | null | nothing to repair |
| `QUEUED_OVERLOAD_TIME` | null | one query at a time, never queued |
| `TRANSACTION_BLOCKED_TIME` | null | no concurrent writers |
| `CHILD_QUERIES_WAIT_TIME` | null | no child queries |
| `QUERY_RETRY_TIME` | null | no retries |
| `QUERY_RETRY_CAUSE` | null | no retries |
| `FAULT_HANDLING_TIME` | null | no faults |
| `LIST_EXTERNAL_FILES_TIME` | null | no external stages |

### Volume

| column | label | meaning |
|---|---|---|
| `BYTES_SCANNED` | **estimated** | the on-disk `BYTES` of every table the statement names. DuckDB does not report bytes read, and the filter is applied after the scan, so it does not reduce this |
| `PERCENTAGE_SCANNED_FROM_CACHE` | null | not reported by the engine |
| `ROWS_PRODUCED` | measured | exact row count of the materialised result |
| `PARTITIONS_SCANNED` | measured | row groups behind the tables named — DuckDB's micro-partitions. Equal to `PARTITIONS_TOTAL`: the filter is on a computed expression, so nothing is pruned |
| `PARTITIONS_TOTAL` | measured | row groups behind the tables named |
| `BYTES_WRITTEN` | null | nothing is written to a permanent table |
| `BYTES_WRITTEN_TO_RESULT` | null | no result cache |
| `BYTES_READ_FROM_RESULT` | null | no result cache |
| `ROWS_WRITTEN_TO_RESULT` | null | no result cache |
| `ROWS_INSERTED` | null | SELECT |
| `ROWS_UPDATED` | null | SELECT |
| `ROWS_DELETED` | null | SELECT |
| `ROWS_UNLOADED` | null | SELECT |
| `BYTES_DELETED` | null | SELECT |
| `BYTES_SPILLED_TO_LOCAL_STORAGE` | null | not reported by the engine |
| `BYTES_SPILLED_TO_REMOTE_STORAGE` | null | no remote storage |
| `BYTES_SENT_OVER_THE_NETWORK` | null | the engine is in-process |
| `QUERY_LOAD_PERCENT` | null | no warehouse load metric |

### Hashes

| column | label | meaning |
|---|---|---|
| `QUERY_HASH` | derived | SHA-256 of `QUERY_TEXT`, first 32 hex characters |
| `QUERY_HASH_VERSION` | derived | `1` |
| `QUERY_PARAMETERIZED_HASH` | derived | the same hash of the text with every literal replaced by `?`, so the four filter constants of one shape collide |
| `QUERY_PARAMETERIZED_HASH_VERSION` | derived | `1` |

### Not applicable here

All NULL: `OUTBOUND_DATA_TRANSFER_CLOUD`, `OUTBOUND_DATA_TRANSFER_REGION`,
`OUTBOUND_DATA_TRANSFER_BYTES`, `INBOUND_DATA_TRANSFER_CLOUD`,
`INBOUND_DATA_TRANSFER_REGION`, `INBOUND_DATA_TRANSFER_BYTES`,
`CREDITS_USED_CLOUD_SERVICES`, `EXTERNAL_FUNCTION_TOTAL_INVOCATIONS`,
`EXTERNAL_FUNCTION_TOTAL_SENT_ROWS`, `EXTERNAL_FUNCTION_TOTAL_RECEIVED_ROWS`,
`EXTERNAL_FUNCTION_TOTAL_SENT_BYTES`, `EXTERNAL_FUNCTION_TOTAL_RECEIVED_BYTES`,
`QUERY_ACCELERATION_BYTES_SCANNED`, `QUERY_ACCELERATION_PARTITIONS_SCANNED`,
`QUERY_ACCELERATION_UPPER_LIMIT_SCALE_FACTOR`.

There is no cross-region transfer, no billing, no external function and no query
acceleration service on a local engine.

## data/tables.csv

The catalogue. Describes the warehouse rather than the state of the demo, so
`reset` leaves it alone.

| column | label | meaning |
|---|---|---|
| `ROW_COUNT` | measured | `select count(*)` |
| `BYTES` | measured | blocks the table occupies on disk × the database block size, from `pragma_storage_info` |
| `TABLE_CATALOG` | derived | `ANALYTICS` |
| `TABLE_SCHEMA` | derived | `PUBLIC` |
| `TABLE_NAME` | derived | the DuckDB table name, upper-cased |
| `TABLE_OWNER` | derived | `SYSADMIN` |
| `TABLE_TYPE` | derived | `BASE TABLE` |
| `IS_TRANSIENT` | derived | `NO` |
| `RETENTION_TIME` | derived | `1` day |
| `IS_INSERTABLE_INTO` | derived | `YES` |
| `IS_TYPED` | derived | `YES` |
| `CREATED` | derived | the date the table definition was fixed. The tables are generated from row numbers, so a rebuild is byte-identical and a wall clock would only record when someone last ran the script |
| `LAST_ALTERED` | derived | as `CREATED`; nothing alters them |
| `LAST_DDL` | derived | as `CREATED` |
| `LAST_DDL_BY` | derived | `BAILEY` |
| `AUTO_CLUSTERING_ON` | derived | `NO` |
| `COMMENT` | derived | what the table is |
| `OWNER_ROLE_TYPE` | derived | `ROLE` |
| `IS_TEMPORARY` | derived | `NO` |
| `IS_ICEBERG` | derived | `NO` |
| `IS_DYNAMIC` | derived | `NO` |
| `IS_IMMUTABLE` | derived | `NO` |
| `IS_HYBRID` | derived | `NO` |
| `CLUSTERING_KEY` | null | no clustering keys are defined |
| `SELF_REFERENCING_COLUMN_NAME` | null | not a typed table |
| `REFERENCE_GENERATION` | null | not a typed table |
| `USER_DEFINED_TYPE_CATALOG` | null | no user-defined types |
| `USER_DEFINED_TYPE_SCHEMA` | null | no user-defined types |
| `USER_DEFINED_TYPE_NAME` | null | no user-defined types |
| `COMMIT_ACTION` | null | not a temporary table |

## data/calibration.csv

Not Snowflake's shape, and deliberately not dressed up as it. A shared runner
drifts: a noisy neighbour makes everything slower at once, and a time-ordered
holdout reads that as model error. So a fixed calibration query is re-timed every
ten queries and every reading is divided by the value interpolated to its
position in the batch.

Snowflake has no column for how busy the machine was, so this lives in its own
table with lower-case names rather than being smuggled into `QUERY_HISTORY`.

| column | label | meaning |
|---|---|---|
| `query_id` | derived | joins to `QUERY_HISTORY.QUERY_ID` |
| `batch_name` | derived | the batch, as `QUERY_TAG` |
| `template_id`, `template_label` | derived | which catalogue shape this query came from |
| `warehouse_size` | measured | as `WAREHOUSE_SIZE` |
| `reps` | measured | timed repetitions behind the median |
| `execution_ms` | measured | as `EXECUTION_TIME` |
| `min_execution_ms`, `max_execution_ms` | measured | fastest and slowest repetition |
| `calibration_ms` | measured | the calibration query's runtime, interpolated to this query's position |
| `machine_factor` | derived | `calibration_ms` over the first batch's reference reading |
| `calibrated_execution_ms` | derived | `execution_ms / machine_factor`. **The training target** |

## What the model is allowed to read

`PRE_RUN_COLUMNS` in `src/runtime_model/snowflake.py` is the list of columns that
exist the moment the statement is submitted. Everything else in `QUERY_HISTORY`
is written by the engine once the query has finished.

`features.featurise` projects every row down to `QUERY_TEXT`, `WAREHOUSE_SIZE`
and the two history columns before it builds anything, so an after-the-fact
column is not merely unused — it is not in the dictionary the feature builder
can see. `tests/test_leakage.py` checks that projection against the column lists,
and blanks every after-the-fact column to prove not one feature moves.

| used | from |
|---|---|
| yes | `QUERY_TEXT`, parsed: tables named, joins, group by, order by, window, limit, predicate count, predicate constant |
| yes | `WAREHOUSE_SIZE` |
| yes | `TABLES.ROW_COUNT` and `TABLES.BYTES` for every table the parser found |
| yes | `QUERY_PARAMETERIZED_HASH`, to find what the same shape cost in earlier batches |
| target | `EXECUTION_TIME`, with the runner drift divided out |
| no | `QUERY_TYPE` — every measured query is a SELECT, so the column has no variance here |
| no | `START_TIME` — batches are measured back to back on one runner, so the hour of day would only encode which batch a query came from. In a warehouse with a diurnal load curve it would be a feature |
| no | every other column above, because it is written after the query has run |
