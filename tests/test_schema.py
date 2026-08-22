"""The published input is Snowflake's shape, column for column, in order.

If a column is added, renamed or reordered, this fails. The point of the shape
is that a reader can put data/query_history.csv next to a real ACCOUNT_USAGE
export and see the same header.
"""

import csv

from runtime_model import snowflake
from runtime_model.workload import ROOT

DATA = ROOT / "data"
DOCS = ROOT / "docs"


def header(name: str) -> list[str]:
    with open(DATA / name, newline="") as handle:
        return next(csv.reader(handle))


def test_query_history_has_exactly_the_account_usage_columns_in_order():
    assert header("query_history.csv") == snowflake.QUERY_HISTORY_COLUMNS


def test_tables_has_exactly_the_account_usage_columns_in_order():
    assert header("tables.csv") == snowflake.TABLES_COLUMNS


def test_the_column_lists_are_unique_and_upper_case():
    for columns in (snowflake.QUERY_HISTORY_COLUMNS, snowflake.TABLES_COLUMNS):
        assert len(set(columns)) == len(columns)
        assert all(column == column.upper() for column in columns)


def test_the_catalogue_table_is_populated_and_measured():
    with open(DATA / "tables.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 7
    assert all(int(row["ROW_COUNT"]) > 0 and int(row["BYTES"]) > 0 for row in rows)
    assert all(row["TABLE_CATALOG"] == snowflake.DATABASE_NAME for row in rows)


def test_every_column_is_documented():
    """The data dictionary is the contract; a column missing from it is a gap."""
    text = (DOCS / "data_dictionary.md").read_text()
    missing = [column for column in snowflake.QUERY_HISTORY_COLUMNS + snowflake.TABLES_COLUMNS
               if f"`{column}`" not in text]
    assert missing == []


def test_the_feature_map_names_real_things():
    for entry in snowflake.FEATURE_MAP:
        assert entry["used"] in ("yes", "no", "target")
        assert entry["why"]
