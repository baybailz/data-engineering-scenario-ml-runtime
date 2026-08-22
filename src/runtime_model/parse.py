"""Read a query's shape out of QUERY_TEXT, with nothing but the text.

This is the half of the feature set that a planner also has: which tables the
statement names, how many joins, whether there is a group by, an order by, a
window, a limit, how many predicates sit in the WHERE clause and what constant
each one compares against. No measurement is involved and none is available --
the statement has not run.

The one thing the text alone cannot tell you is how much data is behind those
table names, which is what ACCOUNT_USAGE.TABLES is for: `shape()` takes the
parsed table list and looks ROW_COUNT and BYTES up in it.

Deliberately a regex parser, not a SQL engine. It has to answer eight structural
questions about the statements this repo generates; a dependency that parses
all of Snowflake SQL would be a bigger promise than the model needs.
"""

import re

CTE = re.compile(r"(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
FROM_OR_JOIN = re.compile(r"\b(?:from|join)\s+([a-z_][a-z0-9_.]*)", re.IGNORECASE)
JOIN = re.compile(r"\bjoin\b", re.IGNORECASE)
GROUP_BY = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)
ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)
WINDOW = re.compile(r"\bover\s*\(", re.IGNORECASE)
LIMIT = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)
CONJUNCTION = re.compile(r"\b(?:and|or)\b", re.IGNORECASE)
COMPARISON = re.compile(r"(?:<=|>=|<>|!=|<|>|=)\s*(-?\d+(?:\.\d+)?)")
WHERE = re.compile(r"\bwhere\b", re.IGNORECASE)
CLAUSE_END = re.compile(r"\b(?:group\s+by|order\s+by|having|limit|window|qualify)\b",
                        re.IGNORECASE)
COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def where_clauses(text: str) -> list[str]:
    """The text of each WHERE clause, cut at the end of its own subquery.

    Written by hand rather than as one regex because the clause itself contains
    brackets -- `cast(substr(event_code, 3, 3) as integer) < 200` -- and a
    pattern that stops at the first `)` would throw away the predicate.
    """
    clauses = []
    for match in WHERE.finditer(text):
        depth, start = 0, match.end()
        cursor = start
        while cursor < len(text):
            character = text[cursor]
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                keyword = CLAUSE_END.match(text, cursor)
                if keyword:
                    break
            cursor += 1
        clauses.append(text[start:cursor])
    return clauses


def parse_query_text(text: str) -> dict:
    """The structure of one statement. Every value is readable before it runs."""
    text = COMMENT.sub(" ", text or "")
    ctes = {name.lower() for name in CTE.findall(text)}
    tables, seen = [], set()
    for name in FROM_OR_JOIN.findall(text):
        key = name.split(".")[-1].lower()
        if key in ctes or key in seen:
            continue
        seen.add(key)
        tables.append(key.upper())

    clauses = where_clauses(text)
    predicates = sum(1 + len(CONJUNCTION.findall(clause)) for clause in clauses)
    literals = [float(value) for clause in clauses
                for value in COMPARISON.findall(clause)]
    limits = [int(value) for value in LIMIT.findall(text)]

    return {
        "tables": tables,
        "n_tables": len(tables),
        "n_joins": len(JOIN.findall(text)),
        "has_group_by": 1 if GROUP_BY.search(text) else 0,
        "has_order_by": 1 if ORDER_BY.search(text) else 0,
        "has_window": 1 if WINDOW.search(text) else 0,
        "limit_rows": max(limits) if limits else 0,
        "n_predicates": predicates,
        # The constant the filter compares against, straight out of the text.
        # It is not a selectivity: what fraction of the table it keeps is
        # exactly what the model has to learn.
        "predicate_literal": max(literals) if literals else 0.0,
    }


def shape(text: str, warehouse_size: str, tables: dict) -> dict:
    """The parsed statement plus the size of the tables it names.

    `tables` maps TABLE_NAME to {"rows": ROW_COUNT, "bytes": BYTES}, read from
    the ACCOUNT_USAGE.TABLES copy in data/tables.csv. A table the catalogue does
    not know about contributes nothing rather than a guess.
    """
    from .snowflake import WAREHOUSE_SIZES

    parsed = parse_query_text(text)
    known = [tables[name] for name in parsed["tables"] if name in tables]
    parsed["table_rows"] = sum(int(entry["rows"]) for entry in known)
    parsed["table_bytes"] = sum(int(entry["bytes"]) for entry in known)
    parsed["tables_known"] = len(known)
    parsed["warehouse_size"] = warehouse_size
    parsed["warehouse_threads"] = WAREHOUSE_SIZES.get(warehouse_size, 0)
    return parsed


def table_index(rows: list[dict]) -> dict:
    """ACCOUNT_USAGE.TABLES rows to the lookup `shape` wants."""
    return {str(row["TABLE_NAME"]).upper():
            {"rows": int(row["ROW_COUNT"] or 0), "bytes": int(row["BYTES"] or 0)}
            for row in rows}
