"""The shape of the input: SNOWFLAKE.ACCOUNT_USAGE, column for column.

The measurements are real DuckDB timings taken on the machine that runs this
repository. They are written in the exact column layout of
``SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`` and ``.TABLES``, because that is the
table a team would actually train on. Nothing else about the input is invented:
a column we can measure carries a measurement, a column we can derive carries a
derivation, and a column that does not apply to a local engine is NULL. There
are no filler numbers anywhere in this file.

``PRE_RUN_COLUMNS`` and ``AFTER_THE_FACT_COLUMNS`` partition QUERY_HISTORY into
what exists at submit time and what only exists once the query has finished.
The feature builder is only ever handed the first set; ``FEATURE_MAP`` is the
published version of that decision, rendered on the deck and checked by a test.

    docs/data_dictionary.md   every column, its meaning and its provenance
"""

import hashlib
import re

# ---------------------------------------------------------------- the columns

QUERY_HISTORY_COLUMNS = [
    "QUERY_ID", "QUERY_TEXT", "DATABASE_NAME", "SCHEMA_NAME", "QUERY_TYPE",
    "SESSION_ID", "USER_NAME", "ROLE_NAME", "WAREHOUSE_NAME", "WAREHOUSE_SIZE",
    "WAREHOUSE_TYPE", "CLUSTER_NUMBER", "QUERY_TAG", "EXECUTION_STATUS",
    "ERROR_CODE", "ERROR_MESSAGE", "START_TIME", "END_TIME", "TOTAL_ELAPSED_TIME",
    "BYTES_SCANNED", "PERCENTAGE_SCANNED_FROM_CACHE", "BYTES_WRITTEN",
    "BYTES_WRITTEN_TO_RESULT", "BYTES_READ_FROM_RESULT", "ROWS_PRODUCED",
    "ROWS_INSERTED", "ROWS_UPDATED", "ROWS_DELETED", "ROWS_UNLOADED",
    "BYTES_DELETED", "PARTITIONS_SCANNED", "PARTITIONS_TOTAL",
    "BYTES_SPILLED_TO_LOCAL_STORAGE", "BYTES_SPILLED_TO_REMOTE_STORAGE",
    "BYTES_SENT_OVER_THE_NETWORK", "COMPILATION_TIME", "EXECUTION_TIME",
    "QUEUED_PROVISIONING_TIME", "QUEUED_REPAIR_TIME", "QUEUED_OVERLOAD_TIME",
    "TRANSACTION_BLOCKED_TIME", "OUTBOUND_DATA_TRANSFER_CLOUD",
    "OUTBOUND_DATA_TRANSFER_REGION", "OUTBOUND_DATA_TRANSFER_BYTES",
    "INBOUND_DATA_TRANSFER_CLOUD", "INBOUND_DATA_TRANSFER_REGION",
    "INBOUND_DATA_TRANSFER_BYTES", "LIST_EXTERNAL_FILES_TIME",
    "CREDITS_USED_CLOUD_SERVICES", "RELEASE_VERSION",
    "EXTERNAL_FUNCTION_TOTAL_INVOCATIONS", "EXTERNAL_FUNCTION_TOTAL_SENT_ROWS",
    "EXTERNAL_FUNCTION_TOTAL_RECEIVED_ROWS", "EXTERNAL_FUNCTION_TOTAL_SENT_BYTES",
    "EXTERNAL_FUNCTION_TOTAL_RECEIVED_BYTES", "QUERY_LOAD_PERCENT",
    "IS_CLIENT_GENERATED_STATEMENT", "QUERY_ACCELERATION_BYTES_SCANNED",
    "QUERY_ACCELERATION_PARTITIONS_SCANNED",
    "QUERY_ACCELERATION_UPPER_LIMIT_SCALE_FACTOR", "TRANSACTION_ID",
    "CHILD_QUERIES_WAIT_TIME", "ROLE_TYPE", "QUERY_HASH", "QUERY_HASH_VERSION",
    "QUERY_PARAMETERIZED_HASH", "QUERY_PARAMETERIZED_HASH_VERSION",
    "SECONDARY_ROLE_STATS", "ROWS_WRITTEN_TO_RESULT", "QUERY_RETRY_TIME",
    "QUERY_RETRY_CAUSE", "FAULT_HANDLING_TIME", "USER_TYPE",
    "USER_DATABASE_NAME", "USER_SCHEMA_NAME",
]

TABLES_COLUMNS = [
    "TABLE_CATALOG", "TABLE_SCHEMA", "TABLE_NAME", "TABLE_OWNER", "TABLE_TYPE",
    "IS_TRANSIENT", "CLUSTERING_KEY", "ROW_COUNT", "BYTES", "RETENTION_TIME",
    "SELF_REFERENCING_COLUMN_NAME", "REFERENCE_GENERATION",
    "USER_DEFINED_TYPE_CATALOG", "USER_DEFINED_TYPE_SCHEMA",
    "USER_DEFINED_TYPE_NAME", "IS_INSERTABLE_INTO", "IS_TYPED", "COMMIT_ACTION",
    "CREATED", "LAST_ALTERED", "LAST_DDL", "LAST_DDL_BY", "AUTO_CLUSTERING_ON",
    "COMMENT", "OWNER_ROLE_TYPE", "IS_TEMPORARY", "IS_ICEBERG", "IS_DYNAMIC",
    "IS_IMMUTABLE", "IS_HYBRID",
]

# What exists the moment the statement is submitted. Everything else in
# QUERY_HISTORY is written by the engine after the query has finished, and is
# therefore unusable for predicting the query that has not started yet.
PRE_RUN_COLUMNS = {
    "QUERY_ID", "QUERY_TEXT", "DATABASE_NAME", "SCHEMA_NAME", "QUERY_TYPE",
    "SESSION_ID", "USER_NAME", "ROLE_NAME", "WAREHOUSE_NAME", "WAREHOUSE_SIZE",
    "WAREHOUSE_TYPE", "CLUSTER_NUMBER", "QUERY_TAG", "START_TIME",
    "RELEASE_VERSION", "IS_CLIENT_GENERATED_STATEMENT", "TRANSACTION_ID",
    "ROLE_TYPE", "QUERY_HASH", "QUERY_HASH_VERSION", "QUERY_PARAMETERIZED_HASH",
    "QUERY_PARAMETERIZED_HASH_VERSION", "SECONDARY_ROLE_STATS", "USER_TYPE",
    "USER_DATABASE_NAME", "USER_SCHEMA_NAME", "OUTBOUND_DATA_TRANSFER_CLOUD",
    "OUTBOUND_DATA_TRANSFER_REGION", "INBOUND_DATA_TRANSFER_CLOUD",
    "INBOUND_DATA_TRANSFER_REGION",
}
AFTER_THE_FACT_COLUMNS = [c for c in QUERY_HISTORY_COLUMNS if c not in PRE_RUN_COLUMNS]

# The published version of the decision above: what the deck shows and what the
# leakage test reads. `used` is one of yes / no.
FEATURE_MAP = [
    {"column": "QUERY_TEXT", "used": "yes",
     "why": "parsed: tables, joins, group by, order by, window, limit, predicates"},
    {"column": "WAREHOUSE_SIZE", "used": "yes",
     "why": "X-Small / Small / Medium, applied as 1 / 2 / 4 engine threads"},
    {"column": "QUERY_PARAMETERIZED_HASH", "used": "yes",
     "why": "joins this query to the same shape measured in earlier batches"},
    {"column": "TABLES.ROW_COUNT, TABLES.BYTES", "used": "yes",
     "why": "size of every table the parser found, from the catalogue table"},
    {"column": "QUERY_TYPE", "used": "no",
     "why": "every measured query is a SELECT here, so the column has no variance"},
    {"column": "START_TIME", "used": "no",
     "why": "batches are measured back to back, so the hour only names the batch"},
    {"column": "EXECUTION_TIME", "used": "target",
     "why": "what is being predicted"},
    {"column": "TOTAL_ELAPSED_TIME", "used": "no", "why": "contains the target"},
    {"column": "COMPILATION_TIME", "used": "no",
     "why": "written after the plan is built, not at submit time"},
    {"column": "BYTES_SCANNED", "used": "no",
     "why": "the engine reports it once the scan is over"},
    {"column": "PARTITIONS_SCANNED, PARTITIONS_TOTAL", "used": "no",
     "why": "pruning is decided during the run"},
    {"column": "ROWS_PRODUCED", "used": "no",
     "why": "the answer to the query. Knowing it means the query already ran"},
    {"column": "PERCENTAGE_SCANNED_FROM_CACHE", "used": "no",
     "why": "a property of the run, not of the query"},
    {"column": "BYTES_SPILLED_TO_LOCAL_STORAGE", "used": "no",
     "why": "a spill is a symptom of the runtime being predicted"},
    {"column": "QUEUED_OVERLOAD_TIME", "used": "no",
     "why": "queueing happens after submit"},
    {"column": "QUERY_LOAD_PERCENT", "used": "no",
     "why": "measured across the life of the query"},
]

# ------------------------------------------------------------ the constants we
# set ourselves. One account, one warehouse, one user: they are constants in the
# data because they were constants in the measurement.

DATABASE_NAME = "ANALYTICS"
SCHEMA_NAME = "PUBLIC"
WAREHOUSE_NAME = "COMPUTE_WH"
WAREHOUSE_TYPE = "STANDARD"
USER_NAME = "BAILEY"
ROLE_NAME = "ANALYST"
TABLE_OWNER = "SYSADMIN"

# The one knob that is both a Snowflake column and a real physical difference
# here: warehouse size is applied as the engine's thread count before timing.
WAREHOUSE_SIZES = {"X-Small": 1, "Small": 2, "Medium": 4}
WAREHOUSE_ORDER = list(WAREHOUSE_SIZES)

HASH_VERSION = 1

_LITERAL = re.compile(r"'[^']*'|\b\d+(?:\.\d+)?\b")


def query_hash(text: str) -> str:
    """SHA-256 of the statement, as Snowflake's QUERY_HASH is of its own."""
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def parameterized_hash(text: str) -> str:
    """The same hash with every literal replaced by a placeholder.

    Two queries that differ only in a filter constant share this hash, which is
    what makes "have we run this shape before" answerable before the run.
    """
    return query_hash(_LITERAL.sub("?", text))


def null_row() -> dict:
    """Every QUERY_HISTORY column, all NULL. Callers fill what they know."""
    return dict.fromkeys(QUERY_HISTORY_COLUMNS)


def table_row(name: str, row_count: int, table_bytes: int, created: str,
              comment: str) -> dict:
    """One ACCOUNT_USAGE.TABLES row. ROW_COUNT and BYTES are measured."""
    row = dict.fromkeys(TABLES_COLUMNS)
    row.update({
        "TABLE_CATALOG": DATABASE_NAME,
        "TABLE_SCHEMA": SCHEMA_NAME,
        "TABLE_NAME": name.upper(),
        "TABLE_OWNER": TABLE_OWNER,
        "TABLE_TYPE": "BASE TABLE",
        "IS_TRANSIENT": "NO",
        "ROW_COUNT": row_count,
        "BYTES": table_bytes,
        "RETENTION_TIME": 1,
        "IS_INSERTABLE_INTO": "YES",
        "IS_TYPED": "YES",
        "CREATED": created,
        "LAST_ALTERED": created,
        "LAST_DDL": created,
        "LAST_DDL_BY": USER_NAME,
        "AUTO_CLUSTERING_ON": "NO",
        "COMMENT": comment,
        "OWNER_ROLE_TYPE": "ROLE",
        "IS_TEMPORARY": "NO",
        "IS_ICEBERG": "NO",
        "IS_DYNAMIC": "NO",
        "IS_IMMUTABLE": "NO",
        "IS_HYBRID": "NO",
    })
    return row
