-- Transform: the measured runs with their model features typed the way the
-- model reads them. The flags become yes/no here so the conformed layer can
-- test a closed list, and the filter estimate is derived once, not in four
-- downstream models.
{{ config(unique_key='query_id') }}

with query_run as (
    select * from {{ ref('stg_query_run') }}
),

derived as (
    select
        query_run.query_id,
        query_run.batch_name,
        query_run.template_id,
        query_run.template_label,
        query_run.fact_table,
        query_run.fact_rows,
        query_run.rows_in,
        query_run.bytes_est,
        query_run.n_joins,
        query_run.selectivity,
        query_run.limit_rows,
        query_run.reps,
        query_run.median_seconds,
        query_run.min_seconds,
        query_run.max_seconds,
        query_run.machine_factor,
        query_run.normalized_seconds,
        query_run.cpu_count,
        query_run.duckdb_threads,
        query_run.measured_at,
        case when query_run.has_groupby = 1 then 'yes' else 'no' end as has_groupby,
        case when query_run.has_orderby = 1 then 'yes' else 'no' end as has_orderby,
        case when query_run.has_window = 1 then 'yes' else 'no' end as has_window,
        cast(query_run.fact_rows * query_run.selectivity as bigint) as rows_after_filter_est
    from query_run
)

select
    query_id,
    batch_name,
    template_id,
    template_label,
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
    measured_at
from derived
