-- Conformed: one row per query shape. Selectivity is not part of the shape,
-- so a template is four measured queries that differ only in how much of the
-- table the filter keeps.
{{ config(unique_key='template_key') }}

with query_run as (
    select * from {{ ref('trn_tbl_query_run') }}
),

shaped as (
    select
        query_run.template_id,
        max(query_run.template_label) as template_label,
        max(query_run.fact_table) as fact_table,
        max(query_run.fact_rows) as fact_rows,
        max(query_run.rows_in) as rows_in,
        max(query_run.bytes_est) as bytes_est,
        max(query_run.n_joins) as n_joins,
        max(query_run.has_groupby) as has_groupby,
        max(query_run.has_orderby) as has_orderby,
        max(query_run.has_window) as has_window,
        max(query_run.limit_rows) as limit_rows,
        count(*) as queries_measured
    from query_run
    group by query_run.template_id
)

select
    {{ surrogate_key(['template_id']) }} as template_key,
    template_id,
    template_label,
    fact_table,
    fact_rows,
    rows_in,
    bytes_est,
    n_joins,
    has_groupby,
    has_orderby,
    has_window,
    limit_rows,
    queries_measured,
    current_timestamp as dbt_run_timestamp
from shaped
