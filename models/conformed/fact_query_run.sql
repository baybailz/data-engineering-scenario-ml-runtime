-- Conformed: the measurement fact. Incremental on run_key, so re-running a
-- batch upserts its rows instead of duplicating them.
{{ config(unique_key='run_key') }}

with query_run as (
    select * from {{ ref('trn_tbl_query_run') }}
)

select
    {{ surrogate_key(['query_id']) }} as run_key,
    {{ surrogate_key(['template_id']) }} as template_key,
    query_id,
    template_id,
    batch_name,
    fact_table,
    fact_rows,
    rows_in,
    bytes_est,
    rows_after_filter_est,
    n_joins,
    has_groupby,
    selectivity,
    has_orderby,
    has_window,
    limit_rows,
    reps,
    median_seconds,
    min_seconds,
    max_seconds,
    machine_factor,
    normalized_seconds,
    cpu_count,
    duckdb_threads,
    measured_at,
    current_timestamp as dbt_run_timestamp
from query_run
