-- A predicted runtime below zero is meaningless. The model predicts log
-- seconds and is exponentiated back, so this cannot happen by construction:
-- the test is here to catch the day someone changes the target.
select
    fact_query_prediction.prediction_key,
    fact_query_prediction.predicted_seconds
from {{ ref('fact_query_prediction') }}
where fact_query_prediction.predicted_seconds <= 0
