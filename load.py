"""
Load - create the schema and write the transformed tables into SQLite.

Loads are idempotent: the schema is dropped and recreated on every run, so
running the build twice produces the same warehouse rather than doubling every
fact table. For a project of this size a full rebuild is simpler and safer than
incremental loading, and it takes seconds.

Dimensions load before facts because facts carry foreign keys into them.
"""

import logging
import sqlite3

import pandas as pd

import config

log = logging.getLogger(__name__)

DIMENSION_ORDER = ["dim_date", "dim_location", "dim_crime_type",
                   "dim_carrier", "dim_vendor"]
FACT_ORDER = ["fact_crime", "fact_taxi_trip", "fact_flight"]


def create_schema(conn: sqlite3.Connection) -> None:
    """Run the DDL, dropping and recreating every table."""
    conn.executescript(config.SCHEMA_PATH.read_text())
    conn.commit()
    log.info("Schema created at %s", config.DB_PATH)


def load_tables(conn: sqlite3.Connection, tables: dict[str, pd.DataFrame]) -> dict:
    """Write each table, dimensions first. Returns rows loaded per table."""
    loaded = {}
    for name in DIMENSION_ORDER + FACT_ORDER:
        df = tables[name]
        df.to_sql(name, conn, if_exists="append", index=False)
        loaded[name] = len(df)
        log.info("Loaded %-16s %s rows", name, len(df))
    conn.commit()
    return loaded


def build(tables: dict[str, pd.DataFrame]) -> dict:
    """Create the database and load it. Foreign keys are enforced explicitly -
    SQLite has them off by default, which would let orphan keys through."""
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        create_schema(conn)
        return load_tables(conn, tables)
