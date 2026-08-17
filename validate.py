"""
Validate - post-load data quality checks.

These run against the loaded warehouse, not the dataframes, because the point is
to verify what actually landed in the database. A check that passes in pandas and
fails in SQL has told you nothing useful.

Four checks, each catching a different failure mode:

  row counts    - did anything load at all
  orphan keys   - do all facts resolve to a dimension row
  null rates    - are required columns populated
  measure sanity- are numeric measures inside plausible ranges

Any failure raises. Loading bad data silently is the outcome this exists to
prevent; a build that fails is recoverable, a dashboard built on bad data is not.
"""

import logging
import sqlite3

import config

log = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a data quality check fails."""


def _scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


def check_row_counts(conn) -> list[str]:
    failures = []
    for table in ["fact_crime", "fact_taxi_trip", "fact_flight"]:
        count = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
        log.info("  %-16s %s rows", table, count)
        if count < config.MIN_ROWS_PER_FACT:
            failures.append(f"{table} has only {count} rows "
                            f"(minimum {config.MIN_ROWS_PER_FACT})")
    return failures


def check_orphan_keys(conn) -> list[str]:
    """Every foreign key on a fact must resolve to a dimension row."""
    pairs = [
        ("fact_crime", "date_key", "dim_date"),
        ("fact_crime", "location_key", "dim_location"),
        ("fact_crime", "crime_type_key", "dim_crime_type"),
        ("fact_taxi_trip", "date_key", "dim_date"),
        ("fact_taxi_trip", "vendor_key", "dim_vendor"),
        ("fact_flight", "date_key", "dim_date"),
        ("fact_flight", "carrier_key", "dim_carrier"),
    ]
    failures = []
    for fact, key, dim in pairs:
        orphans = _scalar(conn, f"""
            SELECT COUNT(*) FROM {fact} f
            LEFT JOIN {dim} d ON f.{key} = d.{key}
            WHERE d.{key} IS NULL
        """)
        if orphans > 0:
            failures.append(f"{fact}.{key} has {orphans} orphan rows")
        else:
            log.info("  %-16s %-16s no orphans", fact, key)
    return failures


def check_null_rates(conn) -> list[str]:
    """Required columns must stay under the configured null threshold."""
    required = [
        ("fact_crime", "date_key"),
        ("fact_crime", "crime_type_key"),
        ("fact_taxi_trip", "fare_amount"),
        ("fact_taxi_trip", "trip_distance"),
        ("fact_flight", "carrier_key"),
    ]
    failures = []
    for table, column in required:
        total = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
        if not total:
            continue
        nulls = _scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
        rate = nulls / total
        if rate > config.MAX_NULL_RATE:
            failures.append(f"{table}.{column} is {rate:.1%} null "
                            f"(max {config.MAX_NULL_RATE:.0%})")
        else:
            log.info("  %-16s %-16s %.2f%% null", table, column, rate * 100)
    return failures


def check_measures(conn) -> list[str]:
    """Catch measures that survived cleaning but should not exist."""
    failures = []

    bad_fares = _scalar(conn, "SELECT COUNT(*) FROM fact_taxi_trip WHERE fare_amount <= 0")
    if bad_fares:
        failures.append(f"{bad_fares} taxi trips with non-positive fare")

    bad_dist = _scalar(conn, "SELECT COUNT(*) FROM fact_taxi_trip WHERE trip_distance <= 0")
    if bad_dist:
        failures.append(f"{bad_dist} taxi trips with non-positive distance")

    # A cancelled flight should have no recorded delay. This is a business-rule
    # check rather than a technical one, and it is the kind that catches real
    # source problems.
    contradictions = _scalar(conn, """
        SELECT COUNT(*) FROM fact_flight
        WHERE cancelled = 1 AND arr_delay_min IS NOT NULL
    """)
    if contradictions:
        failures.append(f"{contradictions} cancelled flights carry a delay value")

    if not failures:
        log.info("  measure sanity checks passed")
    return failures


def run_all() -> dict:
    """Run every check. Raises ValidationError if any fail."""
    log.info("Running data quality checks")
    failures = []
    with sqlite3.connect(config.DB_PATH) as conn:
        log.info("Row counts:")
        failures += check_row_counts(conn)
        log.info("Referential integrity:")
        failures += check_orphan_keys(conn)
        log.info("Null rates:")
        failures += check_null_rates(conn)
        log.info("Measures:")
        failures += check_measures(conn)

    if failures:
        for f in failures:
            log.error("FAILED: %s", f)
        raise ValidationError(f"{len(failures)} data quality check(s) failed")

    log.info("All data quality checks passed")
    return {"status": "passed"}
