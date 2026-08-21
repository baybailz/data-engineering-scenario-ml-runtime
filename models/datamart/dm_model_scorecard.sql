-- Datamart: the learning curve. One row per trained model, oldest first, with
-- how much the error moved when the last batch of measurements arrived.
with model_version as (
    select * from {{ ref('dim_model_version') }}
),

sequenced as (
    select
        model_version.*,
        row_number() over (order by model_version.trained_at, model_version.model_version)
            as model_sequence,
        lag(model_version.holdout_mape_pct) over (
            order by model_version.trained_at, model_version.model_version
        ) as previous_mape_pct
    from model_version
)

select
    model_sequence,
    model_version,
    trained_at,
    batches_measured,
    n_train_rows,
    n_holdout_rows,
    holdout_mape_pct,
    mape_ci_low_pct,
    mape_ci_high_pct,
    holdout_r2,
    holdout_mae_seconds,
    cv_mape_pct,
    baseline_mape_pct,
    baseline_mape_pct - holdout_mape_pct as mape_gain_over_baseline,
    holdout_mape_pct - previous_mape_pct as mape_change,
    gate_status,
    current_timestamp as dbt_run_timestamp
from sequenced
order by model_sequence
