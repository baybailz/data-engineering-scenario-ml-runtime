#!/usr/bin/env python3
"""Build the benchmark workload: base tables plus the query catalogue.

Everything here is deterministic. The tables are generated from row numbers
through hash(), never from a random generator, so the same script produces the
same bytes on any machine. The catalogue is the product of the shape knobs
(table size, joins, group by, filter selectivity, order by, window, limit),
shuffled with a fixed seed and cut into batches of 40.

    --rebuild     regenerate workload.duckdb (dropped and rebuilt)
    --catalogue   rewrite incoming/batch_*.csv from the catalogue

workload.duckdb is not committed: it is large and this script rebuilds it in
seconds, which is also the point. The catalogue csv files are committed, so the
queue a visitor sees on the page is exactly the queue the runner measures.
"""

import argparse
import csv
import random
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_DB = ROOT / "workload.duckdb"
INCOMING = ROOT / "incoming"

# Four fact tables. Sizes are chosen so the cheapest query in the catalogue
# still takes tens of milliseconds on four vCPUs: below that, timer noise is
# larger than the effect being modelled.
FACT_TABLES = {
    "fact_event_s": 2_000_000,
    "fact_event_m": 3_000_000,
    "fact_event_l": 5_000_000,
    "fact_event_x": 8_000_000,
}
DIM_ROWS = {"dim_customer_wl": 50_000, "dim_product_wl": 5_000, "dim_region_wl": 200}
# Bytes per row from the declared column widths: the estimate a planner has
# before running anything. Not measured from the file.
FACT_ROW_BYTES = 72
DIM_ROW_BYTES = {"dim_customer_wl": 40, "dim_product_wl": 32, "dim_region_wl": 24}

JOIN_DIMS = [
    ("dim_customer_wl", "customer_id", "customer_segment"),
    ("dim_product_wl", "product_id", "product_category"),
    ("dim_region_wl", "region_id", "region_name"),
]
SELECTIVITIES = [0.02, 0.15, 0.45, 0.90]
LIMITS = [0, 100, 1000]
BATCH_SIZE = 40
N_TEMPLATES = 60
CATALOGUE_SEED = 20260821

CATALOGUE_COLUMNS = [
    "query_id", "template_id", "template_label", "fact_table", "fact_rows",
    "rows_in", "bytes_est", "n_joins", "has_groupby", "selectivity",
    "has_orderby", "has_window", "limit_rows", "query_sql",
]


def build_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Generate the base tables from row numbers, so a rebuild is byte-identical."""
    con.execute(f"""
        create or replace table dim_customer_wl as
        select
            i as customer_id,
            'customer_' || cast(i as varchar) as customer_name,
            (['enterprise', 'mid_market', 'smb', 'public_sector', 'reseller',
              'oem', 'education', 'nonprofit'])[cast((hash(i * 31) % 8) + 1 as bigint)] as customer_segment
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
    threshold = int(round(spec["selectivity"] * 1000))
    filtered = ["        select", ",\n".join(projected),
                f"        from {spec['fact_table']} as fact_event", *join_lines,
                "        where cast(substr(fact_event.event_code, 3, 3) as integer)",
                f"            < {threshold}"]
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
    """60 shape templates x 4 filter selectivities = 240 measurable queries."""
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
        rows_in = shape["fact_rows"] + sum(
            DIM_ROWS[dim] for dim, _, _ in JOIN_DIMS[: shape["n_joins"]])
        bytes_est = shape["fact_rows"] * FACT_ROW_BYTES + sum(
            DIM_ROWS[dim] * DIM_ROW_BYTES[dim] for dim, _, _ in JOIN_DIMS[: shape["n_joins"]])
        for variant, selectivity in enumerate(SELECTIVITIES, start=1):
            spec = dict(shape, selectivity=selectivity, template_id=template_id,
                        rows_in=rows_in, bytes_est=bytes_est,
                        query_id=f"{template_id}_s{variant}")
            spec["template_label"] = label_for(spec)
            spec["query_sql"] = sql_for(spec)
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


def ensure_workload(threads: int = 4) -> duckdb.DuckDBPyConnection:
    """Open workload.duckdb, building it first if this runner has not got one."""
    fresh = not WORKLOAD_DB.exists()
    con = duckdb.connect(str(WORKLOAD_DB))
    con.execute(f"pragma threads={threads}")
    if fresh:
        print("[workload] building base tables")
        build_tables(con)
    return con


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--catalogue", action="store_true")
    args = parser.parse_args()
    if args.rebuild:
        WORKLOAD_DB.unlink(missing_ok=True)
        con = ensure_workload()
        for table_name, rows in FACT_TABLES.items():
            print(f"[workload] {table_name}: {rows:,} rows")
        con.close()
    if args.catalogue or not args.rebuild:
        print(f"[catalogue] {write_catalogue()} batches")


if __name__ == "__main__":
    main()
