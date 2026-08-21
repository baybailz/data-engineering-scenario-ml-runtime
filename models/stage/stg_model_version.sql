-- Stage over the trained-model landing table. One row per training run.
with source as (
    select * from {{ ref('model_version_landing') }}
)

select
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
    passes_gate,
    gate_rule
from source
