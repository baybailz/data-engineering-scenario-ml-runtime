-- Every measured query must be scored by the model that is currently published.
-- If training silently skipped rows, the page would show a scatter with holes
-- in it and the mart would average over a different population than the fact.
with latest_model as (
    select dim_model_version.model_version
    from {{ ref('dim_model_version') }}
    order by dim_model_version.trained_at desc, dim_model_version.model_version desc
    limit 1
),

scored as (
    select fact_query_prediction.query_id
    from {{ ref('fact_query_prediction') }}
    inner join latest_model
        on fact_query_prediction.model_version = latest_model.model_version
)

select fact_query_run.query_id
from {{ ref('fact_query_run') }}
left join scored on fact_query_run.query_id = scored.query_id
where
    scored.query_id is null
    and exists (select 1 from latest_model)
