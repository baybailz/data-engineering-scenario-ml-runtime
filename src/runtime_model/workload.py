#!/usr/bin/env python3
"""Build the warehouse: base tables, the catalogue table, and the query queue.

Everything here is deterministic. The tables are generated from row numbers
through hash(), never from a random generator, so the same script produces the
same bytes on any machine. The catalogue is the product of the shape knobs
(table size, joins, group by, filter constant, order by, window, limit) crossed
with a warehouse size, shuffled with a fixed seed and cut into batches of 40.

    python -m runtime_model.workload --rebuild     rebuild workload.duckdb
    python -m runtime_model.workload --catalogue   rewrite incoming/batch_*.csv
    python -m runtime_model.workload --tables      rewrite data/tables.csv

Two things leave this module. `write_catalogue` writes the queue: a query id, a
warehouse size and the SQL text, and nothing else -- everything the model uses
is parsed back out of that text, so the queue cannot smuggle a feature in.
`table_rows` writes data/tables.csv in the shape of
SNOWFLAKE.ACCOUNT_USAGE.TABLES, with ROW_COUNT and BYTES measured from DuckDB.

workload.duckdb is not committed: it is large and this script rebuilds it in
seconds, which is also the point.
"""

import argparse
import csv
import random
from pathlib import Path

import duckdb

from .snowflake import TABLES_COLUMNS, WAREHOUSE_ORDER, table_row

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_DB = ROOT / "workload.duckdb"
INCOMING = ROOT / "incoming"
TABLES_CSV = ROOT / "data" / "tables.csv"

# Four fact tables. Sizes are chosen so the cheapest query in the catalogue
# still takes tens of milliseconds on four threads: below that, timer noise is
# larger than the effect being modelled.
FACT_TABLES = {
    "fact_event_s": 2_000_000,
    "fact_event_m": 3_000_000,
    "fact_event_l": 5_000_000,
    "fact_event_x": 8_000_000,
}
DIM_ROWS = {"dim_customer_wl": 50_000, "dim_product_wl": 5_000, "dim_region_wl": 200}

JOIN_DIMS = [
    ("dim_customer_wl", "customer_id", "customer_segment"),
    ("dim_product_wl", "product_id", "product_category"),
    ("dim_region_wl", "region_id", "region_name"),
]
# The constant the filter compares against. The event code's middle three
# digits are uniform over 0-999, so a larger constant keeps more rows -- but
# nothing tells the model that, and nothing has to.
FILTER_LITERALS = [20, 150, 450, 900]
LIMITS = [0, 100, 1000]
BATCH_SIZE = 40
N_TEMPLATES = 60
CATALOGUE_SEED = 20260821

# The tables are generated from a definition fixed on this date, so the
# catalogue table carries that rather than a wall clock that would differ on
# every machine that rebuilds the database.
WORKLOAD_CREATED = "2026-08-21T00:00:00Z"

CATALOGUE_COLUMNS = ["query_id", "template_id", "template_label", "warehouse_size",
                     "query_text"]

TABLE_COMMENTS = {
    "fact_event_s": "event fact, small",
    "fact_event_m": "event fact, medium",
    "fact_event_l": "event fact, large",
    "fact_event_x": "event fact, extra large",
    "dim_customer_wl": "customer dimension",
    "dim_product_wl": "product dimension",
    "dim_region_wl": "region dimension",
}


def build_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Generate the base tables from row numbers, so a rebuild is byte-identical."""
    con.execute(f"""
        create or replace table dim_customer_wl as
        select
            i as customer_id,
            'customer_' || cast(i as varchar) as customer_name,
            (['enterprise', 'mid_market', 'smb', 'public_sector', 'reseller',
              'oem', 'education', 'nonprofit'])[cast((hash(i * 31) % 8) + 1 as bigint)]
                as customer_segment
        from range(1, {DIM_ROWS['dim_customer_wl'] + 1}) as t(i)
    """)
    con.execute(f"""
        create or replace table dim_product_wl as
        select
            i as product_id,
            'product_' || cast(i as varchar) as product_name,
            (['storage', 'compute', 'network', 'database', 'analytics', 'security',
              'support', 'training', 'hardware', 'licence', 'services',
              'other'])[cast((hash(i * 17) % 12) + 1 as bigint)] as product_category
        from range(1, {DIM_ROWS['dim_product_wl'] + 1}) as t(i)
    """)
    con.execute(f"""
        create or replace table dim_region_wl as
        select
            i as region_id,
            'region_' || cast(i as varchar) as region_name
        from range(1, {DIM_ROWS['dim_region_wl'] + 1}) as t(i)
    """)
    for table_name, rows in FACT_TABLES.items():
        con.execute(f"""
            create or replace table {table_name} as
            select
                i as event_id,
                cast((hash(i * 2654435761) % {DIM_ROWS['dim_customer_wl']}) + 1 as integer)
                    as customer_id,
                cast((hash(i * 40503) % {DIM_ROWS['dim_product_wl']}) + 1 as integer)
                    as product_id,
                cast((hash(i * 97) % {DIM_ROWS['dim_region_wl']}) + 1 as integer)
                    as region_id,
                timestamp '2024-01-01 00:00:00'
                    + to_seconds(cast(i % 31536000 as bigint)) as event_ts,
                cast((hash(i * 7919) % 20) + 1 as integer) as quantity,
                cast((hash(i * 104729) % 1000000) / 10000.0 as double) as amount,
                'EV' || lpad(cast(hash(i * 15485863) % 1000 as varchar), 3, '0')
                    || '-' || lpad(cast(hash(i * 433494437) % 100000 as varchar), 5, '0')
                    as event_code,
                (['open', 'shipped', 'invoiced', 'paid', 'returned',
                  'cancelled'])[cast((hash(i * 131) % 6) + 1 as bigint)] as status
            from range(1, {rows + 1}) as t(i)
        """)


def sql_for(spec: dict) -> str:
    """One SQL string per catalogue row. One shape, seven knobs."""
    join_lines, dim_attributes = [], []
    for dim_table, join_key, attribute in JOIN_DIMS[: spec["n_joins"]]:
        join_lines.append(
            f"        inner join {dim_table} on fact_event.{join_key} = {dim_table}.{join_key}")
        dim_attributes.append(attribute)

    projected = [f"            {dim_table}.{attribute}"
                 for dim_table, _, attribute in JOIN_DIMS[: spec["n_joins"]]]
    projected += ["            fact_event.customer_id",
                  "            fact_event.product_id",
                  "            fact_event.amount"]
    filtered = ["        select", ",\n".join(projected),
                f"        from {spec['fact_table']} as fact_event", *join_lines,
                "        where cast(substr(fact_event.event_code, 3, 3) as integer)",
                f"            < {spec['filter_literal']}"]
    ctes = [("filtered", "\n".join(filtered))]

    source = "filtered"
    if spec["has_window"]:
        ctes.append(("ranked", "\n".join([
            "        select",
            "            filtered.*,",
            "            row_number() over (",
            "                partition by filtered.customer_id",
            "                order by filtered.amount desc",
            "            ) as amount_rank",
            "        from filtered"])))
        source = "ranked"

    group_columns = (dim_attributes + ["customer_id"]) if spec["has_groupby"] else []
    measures = ["        count(*) as query_rows",
                "        sum(amount) as amount_total",
                "        count(distinct product_id) as products"]
    if spec["has_window"]:
        measures.append("        max(amount_rank) as deepest_rank")
    final = ["    select"]
    final.append(",\n".join([f"        {c}" for c in group_columns] + measures))
    final.append(f"    from {source}")
    if group_columns:
        final.append("    group by " + ", ".join(group_columns))
    if spec["has_orderby"]:
        final.append("    order by amount_total desc")
    if spec["limit_rows"]:
        final.append(f"    limit {spec['limit_rows']}")

    cte_sql = ",\n\n".join(f"    {name} as (\n{body}\n    )" for name, body in ctes)
    return "with\n" + cte_sql + "\n\n" + "\n".join(final)


def label_for(spec: dict) -> str:
    parts = [f"{spec['fact_rows'] / 1_000_000:.0f}M rows",
             f"{spec['n_joins']} join" + ("s" if spec["n_joins"] != 1 else "")]
    parts.append("group by" if spec["has_groupby"] else "no group by")
    if spec["has_window"]:
        parts.append("window")
    if spec["has_orderby"]:
        parts.append("order by")
    parts.append(f"limit {spec['limit_rows']}" if spec["limit_rows"] else "no limit")
    return " · ".join(parts)


def catalogue() -> list[dict]:
    """60 shape templates x 4 filter constants = 240 measurable queries.

    Warehouse size rotates across the four variants of every template, so the
    same shape is timed on one, two and four threads and the size is a real
    feature rather than a constant column.
    """
    shapes = []
    for fact_table, fact_rows in FACT_TABLES.items():
        for n_joins in range(4):
            for has_groupby in (0, 1):
                for has_orderby in (0, 1):
                    for has_window in (0, 1):
                        shapes.append({"fact_table": fact_table, "fact_rows": fact_rows,
                                       "n_joins": n_joins, "has_groupby": has_groupby,
                                       "has_orderby": has_orderby, "has_window": has_window})
    rng = random.Random(CATALOGUE_SEED)
    rng.shuffle(shapes)
    shapes = shapes[:N_TEMPLATES]

    rows = []
    for index, shape in enumerate(shapes, start=1):
        shape = dict(shape, limit_rows=LIMITS[index % len(LIMITS)])
        template_id = f"t{index:02d}"
        for variant, literal in enumerate(FILTER_LITERALS, start=1):
            spec = dict(shape, filter_literal=literal, template_id=template_id,
                        query_id=f"{template_id}_s{variant}",
                        warehouse_size=WAREHOUSE_ORDER[(index + variant) % len(WAREHOUSE_ORDER)])
            spec["template_label"] = label_for(spec)
            spec["query_text"] = sql_for(spec)
            rows.append({column: spec[column] for column in CATALOGUE_COLUMNS})
    rng.shuffle(rows)
    return rows


def write_catalogue() -> int:
    INCOMING.mkdir(parents=True, exist_ok=True)
    for stale in INCOMING.glob("batch_*.csv"):
        stale.unlink()
    rows = catalogue()
    batches = [rows[i:i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    for number, batch in enumerate(batches, start=1):
        path = INCOMING / f"batch_{number:02d}.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CATALOGUE_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(batch)
        print(f"[catalogue] {path.name}: {len(batch)} queries")
    return len(batches)


def table_rows(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """data/tables.csv: ACCOUNT_USAGE.TABLES, measured off this database.

    ROW_COUNT is a count. BYTES is the blocks the table occupies on disk times
    the database's block size, which is what DuckDB can actually tell us -- the
    nearest honest thing to the compressed micro-partition bytes Snowflake
    reports for the same column.
    """
    block_size = con.execute("select block_size from pragma_database_size()").fetchone()[0]
    rows = []
    for name in list(FACT_TABLES) + list(DIM_ROWS):
        count = con.execute(f"select count(*) from {name}").fetchone()[0]
        blocks = con.execute(
            "select count(distinct block_id) from pragma_storage_info(?) where block_id >= 0",
            [name]).fetchone()[0]
        rows.append(table_row(name, int(count), int(blocks) * int(block_size),
                              WORKLOAD_CREATED, TABLE_COMMENTS[name]))
    return rows


def write_tables(con: duckdb.DuckDBPyConnection) -> int:
    rows = table_rows(con)
    TABLES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(TABLES_CSV, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLES_COLUMNS, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{key: ("" if value is None else value) for key, value in row.items()}
                          for row in rows])
    print(f"[tables] data/tables.csv → {len(rows)} tables")
    return len(rows)


def ensure_workload(threads: int = 4) -> duckdb.DuckDBPyConnection:
    """Open workload.duckdb, building it first if this runner has not got one."""
    fresh = not WORKLOAD_DB.exists()
    con = duckdb.connect(str(WORKLOAD_DB))
    con.execute(f"set threads={threads}")
    if fresh:
        print("[workload] building base tables")
        build_tables(con)
        con.execute("checkpoint")
    return con


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--catalogue", action="store_true")
    parser.add_argument("--tables", action="store_true")
    args = parser.parse_args()
    if args.rebuild:
        WORKLOAD_DB.unlink(missing_ok=True)
        con = ensure_workload()
        for table_name, rows in FACT_TABLES.items():
            print(f"[workload] {table_name}: {rows:,} rows")
        write_tables(con)
        con.close()
    elif args.tables:
        con = ensure_workload()
        write_tables(con)
        con.close()
    if args.catalogue or not (args.rebuild or args.tables):
        print(f"[catalogue] {write_catalogue()} batches")


if __name__ == "__main__":
    main()
