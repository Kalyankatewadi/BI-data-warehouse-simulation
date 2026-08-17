"""
Transform - clean the raw extracts and reshape them into dimensions and facts.

The order matters. Dimensions are built first and assigned surrogate keys, then
facts are joined against those dimensions to pick up the keys. A fact row whose
dimension lookup fails is dropped and counted, never loaded with a null key -
a fact referencing a dimension that does not exist is an orphan, and orphans
silently break every aggregate that joins through them.
"""

import logging

import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)


# BTS renames its carrier and date columns between releases, so the transform
# detects which variant is present rather than hardcoding one. A schema change
# in the source should not require editing three places in this file.
CARRIER_COL_CANDIDATES = [
    "OP_UNIQUE_CARRIER", "OP_CARRIER", "IATA_CODE_Reporting_Airline",
    "Reporting_Airline", "Operating_Airline", "CARRIER",
]
DATE_COL_CANDIDATES = ["FL_DATE", "FlightDate", "FL_DATE_1"]
CITY_COL_CANDIDATES = ["ORIGIN_CITY_NAME", "OriginCityName"]


def _find_column(df, candidates, label):
    """Return the first candidate column present, or raise a useful error."""
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(
        f"No {label} column found. Looked for {candidates}. "
        f"Columns present: {list(df.columns)[:15]}"
    )


VIOLENT_CRIMES = {
    "BATTERY", "ASSAULT", "ROBBERY", "HOMICIDE",
    "CRIM SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT",
}


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def profile(df: pd.DataFrame, name: str) -> dict:
    """Report shape, null rates and duplicates before anything is changed.

    Profiling first is the point. Deciding how to clean a column before knowing
    its null rate is guessing, and the profile output is what justifies the
    cleaning rules further down.
    """
    report = {
        "source": name,
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "null_rates": {c: round(df[c].isna().mean(), 4) for c in df.columns},
    }
    log.info("Profile %-7s rows=%-8s dupes=%-6s", name, report["rows"],
             report["duplicate_rows"])
    for col, rate in report["null_rates"].items():
        if rate > 0:
            log.info("    %-24s %.1f%% null", col, rate * 100)
    return report


# ---------------------------------------------------------------------------
# Conformed dimensions
# ---------------------------------------------------------------------------

def build_dim_date() -> pd.DataFrame:
    """Generate one row per calendar day across the configured range."""
    dates = pd.date_range(config.DATE_DIM_START, config.DATE_DIM_END, freq="D")
    return pd.DataFrame({
        "date_key": dates.strftime("%Y%m%d").astype(int),
        "full_date": dates.strftime("%Y-%m-%d"),
        "year": dates.year,
        "quarter": dates.quarter,
        "month": dates.month,
        "month_name": dates.strftime("%B"),
        "day": dates.day,
        "day_of_week": dates.dayofweek,
        "day_name": dates.strftime("%A"),
        "week_of_year": dates.isocalendar().week.astype(int),
        "is_weekend": (dates.dayofweek >= 5).astype(int),
    })


def build_dim_location(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Collect every city appearing in any source into one conformed dimension.

    Cities are title-cased and stripped so that "chicago", "CHICAGO " and
    "Chicago" collapse to one row. Without that normalisation the same city
    arrives from three sources as three different dimension members, and the
    conformed dimension stops conforming anything.
    """
    cities = [("Chicago", "IL")]                      # crime source is Chicago-only
    cities.append(("New York", "NY"))                 # taxi source is NYC-only

    flights = frames.get("flight")
    city_col = next((c for c in CITY_COL_CANDIDATES
                     if flights is not None and c in flights.columns), None)
    if city_col:
        for raw in flights[city_col].dropna().unique():
            city = str(raw).split(",")[0].strip().title()
            state = str(raw).split(",")[1].strip() if "," in str(raw) else None
            if city:
                cities.append((city, state))

    dim = (pd.DataFrame(cities, columns=["city", "state"])
             .drop_duplicates(subset=["city"])
             .reset_index(drop=True))
    dim["country"] = "USA"
    dim.insert(0, "location_key", range(1, len(dim) + 1))
    log.info("dim_location: %s cities", len(dim))
    return dim


# ---------------------------------------------------------------------------
# Source-specific dimensions
# ---------------------------------------------------------------------------

def build_dim_crime_type(crime: pd.DataFrame) -> pd.DataFrame:
    dim = (crime[["primary_type", "description"]]
           .fillna({"description": "UNSPECIFIED"})
           .drop_duplicates()
           .reset_index(drop=True))
    dim["is_violent"] = dim["primary_type"].isin(VIOLENT_CRIMES).astype(int)
    dim.insert(0, "crime_type_key", range(1, len(dim) + 1))
    log.info("dim_crime_type: %s combinations", len(dim))
    return dim


def build_dim_carrier(flight: pd.DataFrame) -> pd.DataFrame:
    code_col = _find_column(flight, CARRIER_COL_CANDIDATES, "carrier")
    name_col = "CARRIER_NAME" if "CARRIER_NAME" in flight.columns else None

    cols = [code_col] + ([name_col] if name_col else [])
    dim = flight[cols].drop_duplicates(subset=[code_col]).copy()
    dim.columns = ["carrier_code"] + (["carrier_name"] if name_col else [])
    if not name_col:
        # BTS does not always ship the airline name alongside the code. The
        # code alone is a valid dimension member; the name is a nice-to-have.
        dim["carrier_name"] = None
    dim = dim.dropna(subset=["carrier_code"]).reset_index(drop=True)
    dim.insert(0, "carrier_key", range(1, len(dim) + 1))
    log.info("dim_carrier: %s carriers", len(dim))
    return dim


def build_dim_vendor(taxi: pd.DataFrame) -> pd.DataFrame:
    vendors = sorted(taxi["VendorID"].dropna().unique())
    names = {1: "Creative Mobile Technologies", 2: "VeriFone Inc."}
    dim = pd.DataFrame({
        "vendor_key": range(1, len(vendors) + 1),
        "vendor_id": [int(v) for v in vendors],
        "vendor_name": [names.get(int(v), "Unknown") for v in vendors],
    })
    log.info("dim_vendor: %s vendors", len(dim))
    return dim


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def _to_date_key(series: pd.Series) -> pd.Series:
    """Convert a datetime column to the YYYYMMDD integer key."""
    # format="mixed" stops pandas warning about per-element inference. BTS ships
    # dates as "1/1/2024 12:00:00 AM" while Socrata sends ISO timestamps, so a
    # single explicit format string would break one source or the other.
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    return parsed.dt.strftime("%Y%m%d").astype("Int64")


class ExcessiveDropError(Exception):
    """Raised when a fact loses more source rows than the threshold allows."""


def _drop_orphans(fact: pd.DataFrame, key: str, valid: set, label: str):
    """Remove fact rows whose dimension key is missing, and fail if too many go.

    Dropping orphans protects referential integrity, but a high drop rate means
    a dimension is incomplete rather than that the data is bad. The first build
    of this warehouse discarded 94% of crime rows because dim_date ended before
    the source data did, and every downstream check still passed - the checks
    validated what loaded, not what vanished. Hence this guard.
    """
    before = len(fact)
    fact = fact[fact[key].isin(valid)].copy()
    dropped = before - len(fact)
    if not before:
        return fact, 0

    rate = dropped / before
    if dropped:
        log.warning("%s: dropped %s rows with unmatched %s (%.2f%%)",
                    label, dropped, key, rate * 100)
    if rate > config.MAX_DROP_RATE:
        raise ExcessiveDropError(
            f"{label}: {rate:.1%} of rows dropped on {key} "
            f"(threshold {config.MAX_DROP_RATE:.0%}). The dimension is likely "
            f"missing members that exist in the source - check the range or "
            f"grain of the dimension before loosening this threshold."
        )
    return fact, dropped


def build_fact_crime(crime, dim_date, dim_location, dim_crime_type):
    df = crime.copy()

    # Cleaning, each rule justified by the profile output:
    df = df.drop_duplicates(subset=["case_number"])        # dupes seen in source
    df["description"] = df["description"].fillna("UNSPECIFIED")
    df["date_key"] = _to_date_key(df["date"])
    df = df.dropna(subset=["date_key", "primary_type"])    # unusable without these

    type_lookup = dim_crime_type.set_index(["primary_type", "description"])["crime_type_key"]
    df["crime_type_key"] = pd.MultiIndex.from_frame(
        df[["primary_type", "description"]]
    ).map(type_lookup)

    chicago_key = int(dim_location.loc[dim_location.city == "Chicago", "location_key"].iloc[0])
    df["location_key"] = chicago_key

    df["arrest_made"] = df["arrest"].astype(str).str.lower().isin(["true", "1"]).astype(int)
    df["domestic"] = df["domestic"].astype(str).str.lower().isin(["true", "1"]).astype(int)
    df["incident_count"] = 1

    fact = df[["date_key", "location_key", "crime_type_key", "case_number",
               "district", "arrest_made", "domestic", "incident_count"]]
    fact = fact.dropna(subset=["crime_type_key"])
    fact, _ = _drop_orphans(fact, "date_key", set(dim_date.date_key), "fact_crime")
    fact = fact.astype({"date_key": int, "crime_type_key": int})
    log.info("fact_crime: %s rows", len(fact))
    return fact


def build_fact_taxi(taxi, dim_date, dim_location, dim_vendor):
    df = taxi.copy()
    pickup = pd.to_datetime(df["tpep_pickup_datetime"], errors="coerce")
    df["date_key"] = pickup.dt.strftime("%Y%m%d").astype("Int64")
    df["pickup_hour"] = pickup.dt.hour

    # Business rules, not arbitrary filtering. Refunds appear as negative fares
    # and zero-distance trips are data errors or immediate cancellations; both
    # distort any average fare or distance measure if left in.
    before = len(df)
    df = df[(df["fare_amount"] > 0) & (df["trip_distance"] > 0)]
    log.info("fact_taxi: removed %s rows failing fare/distance rules", before - len(df))

    vendor_lookup = dim_vendor.set_index("vendor_id")["vendor_key"]
    df["vendor_key"] = df["VendorID"].map(vendor_lookup)

    nyc_key = int(dim_location.loc[dim_location.city == "New York", "location_key"].iloc[0])
    df["location_key"] = nyc_key
    df["trip_count"] = 1

    fact = df[["date_key", "location_key", "vendor_key", "pickup_hour",
               "passenger_count", "trip_distance", "fare_amount",
               "tip_amount", "total_amount", "trip_count"]]
    fact = fact.dropna(subset=["date_key", "vendor_key"])
    fact, _ = _drop_orphans(fact, "date_key", set(dim_date.date_key), "fact_taxi")
    fact = fact.astype({"date_key": int, "vendor_key": int})
    log.info("fact_taxi_trip: %s rows", len(fact))
    return fact


def build_fact_flight(flight, dim_date, dim_location, dim_carrier):
    df = flight.copy()
    date_col = _find_column(df, DATE_COL_CANDIDATES, "flight date")
    code_col = _find_column(df, CARRIER_COL_CANDIDATES, "carrier")
    city_col = _find_column(df, CITY_COL_CANDIDATES, "origin city")

    df["date_key"] = _to_date_key(df[date_col])

    carrier_lookup = dim_carrier.set_index("carrier_code")["carrier_key"]
    df["carrier_key"] = df[code_col].map(carrier_lookup)

    # BTS city names arrive as "Allentown/Bethlehem/Easton, PA" - split on the
    # comma to separate city from state, and title-case so the same city from a
    # different source collapses to one dimension member.
    city = (df[city_col].astype(str)
            .str.split(",").str[0].str.strip().str.title())
    loc_lookup = dim_location.set_index("city")["location_key"]
    df["location_key"] = city.map(loc_lookup)

    df["cancelled"] = df["CANCELLED"].fillna(0).astype(int)
    df["flight_count"] = 1
    df = df.rename(columns={"DEP_DELAY": "dep_delay_min",
                            "ARR_DELAY": "arr_delay_min",
                            "ORIGIN": "origin_airport",
                            "DEST": "dest_airport"})

    fact = df[["date_key", "location_key", "carrier_key", "origin_airport",
               "dest_airport", "dep_delay_min", "arr_delay_min",
               "cancelled", "flight_count"]]
    fact = fact.dropna(subset=["date_key", "carrier_key", "location_key"])
    fact, _ = _drop_orphans(fact, "date_key", set(dim_date.date_key), "fact_flight")
    fact = fact.astype({"date_key": int, "carrier_key": int, "location_key": int})
    log.info("fact_flight: %s rows", len(fact))
    return fact


def transform_all(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Profile, clean and reshape everything into load-ready tables."""
    for name, df in raw.items():
        profile(df, name)

    dim_date = build_dim_date()
    dim_location = build_dim_location(raw)
    dim_crime_type = build_dim_crime_type(raw["crime"])
    dim_carrier = build_dim_carrier(raw["flight"])
    dim_vendor = build_dim_vendor(raw["taxi"])

    return {
        "dim_date": dim_date,
        "dim_location": dim_location,
        "dim_crime_type": dim_crime_type,
        "dim_carrier": dim_carrier,
        "dim_vendor": dim_vendor,
        "fact_crime": build_fact_crime(raw["crime"], dim_date, dim_location, dim_crime_type),
        "fact_taxi_trip": build_fact_taxi(raw["taxi"], dim_date, dim_location, dim_vendor),
        "fact_flight": build_fact_flight(raw["flight"], dim_date, dim_location, dim_carrier),
    }
