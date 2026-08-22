"""Query runtime model: measure, train, predict, publish.

A standalone solution, not a pipeline. DuckDB appears in exactly one place --
as the engine whose queries are being timed. Nothing here is a warehouse.

    workload   builds the tables and the query catalogue that gets measured
    measure    times a batch of queries and calibrates the readings
    features   the feature vector, one place, used by training and by scoring
    train      fits the model, scores it, gates it, exports it to ONNX
    predict    loads the published model and scores a query shape
    report     the tables the page reads: predictions, model versions, SLA
"""

__all__ = ["features", "measure", "predict", "report", "train", "workload"]
