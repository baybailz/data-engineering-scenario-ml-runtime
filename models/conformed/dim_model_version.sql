-- Conformed: one row per trained model, with the metrics it was scored on and
-- whether it cleared the gate. The gate is a column, not a build failure: a
-- model that misses it still ships and still says so.
{{ config(unique_key='model_version_key') }}

with model_version as (
    select * from {{ ref('stg_model_version') }}
),

flagged as (
    select
        model_version.*,
        case when model_version.passes_gate then 'pass' else 'fail' end as gate_status
    from model_version
)

select
    {{ surrogate_key(['model_version']) }} as model_version_key,
    model_version,
    trained_at,
    batches_measured,
    n_train_rows,
    n_holdout_rows,
    model_kind,
    holdout_mae_seconds,
    holdout_mape_pct,
    mape_ci_low_pct,
    mape_ci_high_pct,
    holdout_r2,
    cv_mape_pct,
    baseline_mape_pct,
    gate_status,
    gate_rule,
    current_timestamp as dbt_run_timestamp
from flagged
