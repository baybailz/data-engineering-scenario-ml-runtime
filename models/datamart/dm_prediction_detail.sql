-- Datamart: the published model's prediction for every measured query, joined
-- to the shape it came from. The console reads this, so the page does no joins
-- and cannot join them differently from the SLA mart next to it.
with latest_model as (
    select dim_model_version.model_version
    from {{ ref('dim_model_version') }}
    order by dim_model_version.trained_at desc, dim_model_version.model_version desc
    limit 1
),

prediction as (
    select fact_query_prediction.*
    from {{ ref('fact_query_prediction') }}
    inner join latest_model
        on fact_query_prediction.model_version = latest_model.model_version
),

query_run as (
    select * from {{ ref('fact_query_run') }}
),

query_template as (
    select * from {{ ref('dim_query_template') }}
),

joined as (
    select
        prediction.model_version,
        prediction.query_id,
        prediction.template_id,
        prediction.actual_seconds,
        prediction.predicted_seconds,
        prediction.error_seconds,
        prediction.abs_pct_error,
        prediction.prediction_scope,
        query_template.template_label,
        query_template.n_joins,
        query_template.has_groupby,
        query_template.has_orderby,
        query_template.has_window,
        query_run.selectivity,
        query_run.rows_in,
        query_run.batch_name
    from prediction
    inner join query_run on prediction.run_key = query_run.run_key
    inner join query_template on prediction.template_key = query_template.template_key
)

select
    model_version,
    query_id,
    template_id,
    template_label,
    batch_name,
    n_joins,
    has_groupby,
    has_orderby,
    has_window,
    selectivity,
    rows_in,
    actual_seconds,
    predicted_seconds,
    error_seconds,
    abs_pct_error,
    prediction_scope,
    current_timestamp as dbt_run_timestamp
from joined
order by abs_pct_error desc
