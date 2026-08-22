"""Reading a query's shape out of its text, which is all a planner gets."""

import pytest

from runtime_model.parse import parse_query_text, shape, where_clauses
from runtime_model.workload import catalogue, sql_for

SPEC = {"fact_table": "fact_event_l", "n_joins": 2, "has_groupby": 1, "has_orderby": 1,
        "has_window": 1, "limit_rows": 100, "filter_literal": 450}


def test_a_catalogue_query_parses_to_the_shape_it_was_built_from():
    parsed = parse_query_text(sql_for(SPEC))
    assert parsed["tables"] == ["FACT_EVENT_L", "DIM_CUSTOMER_WL", "DIM_PRODUCT_WL"]
    assert parsed["n_tables"] == 3
    assert parsed["n_joins"] == 2
    assert parsed["has_group_by"] == 1
    assert parsed["has_order_by"] == 1
    assert parsed["has_window"] == 1
    assert parsed["limit_rows"] == 100
    assert parsed["n_predicates"] == 1
    assert parsed["predicate_literal"] == 450


def test_cte_names_are_not_tables():
    """`from filtered` is a common table expression, not something with rows."""
    parsed = parse_query_text(sql_for(SPEC))
    assert "FILTERED" not in parsed["tables"]
    assert "RANKED" not in parsed["tables"]


def test_the_predicate_survives_the_brackets_inside_it():
    """cast(substr(event_code, 3, 3) as integer) < 450 -- the 3s are not the literal."""
    clause = where_clauses(sql_for(SPEC))[0]
    assert "450" in clause
    assert parse_query_text(sql_for(SPEC))["predicate_literal"] == 450


def test_no_predicate_and_no_limit_read_as_zero():
    parsed = parse_query_text("select count(*) from fact_event_s")
    assert parsed["n_predicates"] == 0
    assert parsed["predicate_literal"] == 0.0
    assert parsed["limit_rows"] == 0
    assert parsed["n_joins"] == 0


def test_two_predicates_are_counted():
    parsed = parse_query_text(
        "select a from fact_event_s where quantity > 5 and amount < 900 limit 10")
    assert parsed["n_predicates"] == 2
    assert parsed["predicate_literal"] == 900
    assert parsed["limit_rows"] == 10


def test_comments_do_not_become_structure():
    parsed = parse_query_text("-- group by nothing\nselect a from fact_event_s")
    assert parsed["has_group_by"] == 0


def test_shape_adds_the_table_sizes_and_the_warehouse(tables):
    parsed = shape(sql_for(SPEC), "Small", tables)
    assert parsed["warehouse_threads"] == 2
    assert parsed["table_rows"] == 5_000_000 + 50_000 + 5_000
    assert parsed["table_bytes"] > 0
    assert parsed["tables_known"] == 3


def test_an_unknown_table_contributes_nothing_rather_than_a_guess(tables):
    parsed = shape("select count(*) from not_in_the_catalogue", "Medium", tables)
    assert parsed["table_rows"] == 0
    assert parsed["tables_known"] == 0


def test_every_catalogue_query_parses(tables):
    """240 queries, and the parser has to find a table and a warehouse in each."""
    for query in catalogue():
        parsed = shape(query["query_text"], query["warehouse_size"], tables)
        assert parsed["tables_known"] == parsed["n_tables"] >= 1
        assert parsed["table_rows"] >= 2_000_000
        assert parsed["warehouse_threads"] in (1, 2, 4)
        assert parsed["predicate_literal"] in (20, 150, 450, 900)


def test_shape_rejects_nothing_but_reports_an_unknown_warehouse_as_zero(tables):
    assert shape("select 1", "Jumbo", tables)["warehouse_threads"] == 0
    with pytest.raises(TypeError):
        parse_query_text(object())
