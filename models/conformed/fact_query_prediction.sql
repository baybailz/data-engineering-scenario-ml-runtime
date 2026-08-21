-- Conformed: one row per query per model version. Incremental on
-- prediction_key, so every model that has ever been trained keeps its
-- predictions and the learning curve is a query, not a log file.
{{ config(unique_key='prediction_key') }}

with prediction as (
    select * from {{ ref('trn_tbl_query_prediction') }}
)

select
    prediction_key,
    {{ surrogate_key(['query_id']) }} as run_key,
    {{ surrogate_key(['template_id']) }} as template_key,
    {{ surrogate_key(['model_version']) }} as model_version_key,
    model_version,
    query_id,
    template_id,
    actual_seconds,
    predicted_seconds,
    error_seconds,
    abs_pct_error,
    prediction_scope,
    predicted_at,
    current_timestamp as dbt_run_timestamp
from prediction
