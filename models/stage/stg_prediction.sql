-- Stage over the prediction landing table written by scripts/train.py.
-- One row per measured query per trained model version.
with source as (
    select * from {{ ref('query_prediction_landing') }}
)

select
    model_version,
    query_id,
    actual_seconds,
    predicted_seconds,
    abs_pct_error,
    in_holdout,
    predicted_at
from source
