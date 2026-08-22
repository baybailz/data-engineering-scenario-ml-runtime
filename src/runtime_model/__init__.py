"""Query runtime model: measure, train, predict, publish.

A standalone solution, not a pipeline. DuckDB appears in exactly one place --
as the engine whose queries are being timed. Nothing here is a warehouse; the
input is written in a warehouse's shape.

    snowflake  the ACCOUNT_USAGE column layout, and which half of it is pre-run
    workload   builds the tables, the catalogue table and the query queue
    parse      reads a query's shape out of QUERY_TEXT, with nothing but the text
    measure    times a batch and writes it as QUERY_HISTORY rows
    features   the feature vector, and the projection that keeps it pre-run
    train      fits the model, scores it, gates it, exports it to ONNX
    predict    loads the published model and scores a statement
    report     the tables the page reads: predictions, model versions, SLA
"""

__all__ = ["features", "measure", "parse", "predict", "report", "snowflake", "train",
           "workload"]
