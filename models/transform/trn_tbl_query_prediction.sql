-- Transform: put every prediction next to the run it was predicting and work
-- out the error. The prediction is of calibrated seconds, so it is compared
-- with the calibrated reading, not the raw stopwatch value.
{{ config(unique_key='prediction_key') }}

with prediction as (
    select * from {{ ref('stg_prediction') }}
),

query_run as (
    select * from {{ ref('trn_tbl_query_run') }}
),

joined as (
    select
        prediction.model_version,
        prediction.query_id,
        prediction.predicted_seconds,
        prediction.in_holdout,
        prediction.predicted_at,
        query_run.template_id,
        query_run.template_label,
        query_run.batch_name,
        query_run.n_joins,
        query_run.has_groupby,
        query_run.has_orderby,
        query_run.has_window,
        query_run.selectivity,
        query_run.rows_in,
        query_run.normalized_seconds,
        prediction.predicted_seconds - query_run.normalized_seconds as error_seconds,
        abs(prediction.predicted_seconds - query_run.normalized_seconds)
        / query_run.normalized_seconds * 100 as abs_pct_error
    from prediction
    inner join query_run on prediction.query_id = query_run.query_id
)

select
    {{ surrogate_key(['query_id', 'model_version']) }} as prediction_key,
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
    normalized_seconds as actual_seconds,
    predicted_seconds,
    error_seconds,
    abs_pct_error,
    case when in_holdout = 1 then 'holdout' else 'cross_validated' end as prediction_scope,
    predicted_at
from joined
