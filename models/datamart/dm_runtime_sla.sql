-- Datamart: what the prediction is for. One row per query shape, the runtime
-- the latest model expects against the runtime that was measured, and whether
-- the shape breaches the SLA. The verdict column is the one an operator reads:
-- a missed breach is a page at 3am, a false alarm is a pool sized too big.
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

query_template as (
    select * from {{ ref('dim_query_template') }}
),

per_template as (
    select
        prediction.template_id,
        max(query_template.template_label) as template_label,
        count(*) as queries,
        median(prediction.actual_seconds) as p50_actual_seconds,
        median(prediction.predicted_seconds) as p50_predicted_seconds,
        max(prediction.actual_seconds) as worst_actual_seconds,
        max(prediction.predicted_seconds) as worst_predicted_seconds,
        avg(prediction.abs_pct_error) as mean_abs_pct_error
    from prediction
    inner join query_template on prediction.template_key = query_template.template_key
    group by prediction.template_id
),

judged as (
    select
        per_template.*,
        per_template.worst_actual_seconds > {{ var('sla_seconds') }} as actual_breach,
        per_template.worst_predicted_seconds > {{ var('sla_seconds') }} as predicted_breach
    from per_template
)

select
    template_id,
    template_label,
    queries,
    p50_actual_seconds,
    p50_predicted_seconds,
    worst_actual_seconds,
    worst_predicted_seconds,
    mean_abs_pct_error,
    case
        when predicted_breach and actual_breach then 'breach_called'
        when not predicted_breach and not actual_breach then 'inside_sla'
        when actual_breach then 'missed_breach'
        else 'false_alarm'
    end as sla_verdict,
    {{ var('sla_seconds') }} as sla_seconds,
    current_timestamp as dbt_run_timestamp
from judged
order by worst_actual_seconds desc
