"""
Extract - pull raw data from the three sources into data/raw/.

Each source has different access characteristics, and the code reflects that
rather than pretending they are uniform:

  Chicago Crime  - Socrata REST API, paged
  NYC Taxi       - single parquet file over HTTPS, large, sampled after download
  Airline On-Time- no clean public API, manual download (see README)

There is also a --sample mode that writes small synthetic fixtures matching each
source's real schema. That exists so the pipeline can be tested end to end
without three large downloads. Fixtures are clearly labelled and are never
presented as real data.
"""

import logging

import numpy as np
import pandas as pd
import requests

import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Real extracts
# ---------------------------------------------------------------------------

def extract_chicago_crime(limit: int = None) -> pd.DataFrame:
    """Pull crime incidents from the Chicago Socrata API.

    Socrata caps a single response at 50,000 rows, so anything larger has to be
    paged with $offset. We request only the columns we model - pulling all 22
    and discarding most wastes bandwidth and makes the transform harder to read.
    """
    limit = limit or config.CHICAGO_CRIME_LIMIT
    page_size = 50_000
    fields = "case_number,date,primary_type,description,arrest,domestic,district"

    # $where restricts to the analysis window and $order makes paging stable -
    # without an explicit sort, Socrata may return overlapping or missing rows
    # across pages because the underlying order is not guaranteed.
    where = (f"date >= '{config.ANALYSIS_START}T00:00:00' "
             f"AND date <= '{config.ANALYSIS_END}T23:59:59'")

    frames, offset = [], 0
    while offset < limit:
        batch = min(page_size, limit - offset)
        log.info("Chicago crime: requesting rows %s-%s", offset, offset + batch)
        response = requests.get(
            config.CHICAGO_CRIME_API,
            params={"$limit": batch, "$offset": offset, "$select": fields,
                    "$where": where, "$order": "date"},
            timeout=120,
        )
        response.raise_for_status()
        page = pd.DataFrame(response.json())
        if page.empty:
            break                      # source exhausted before we hit the cap
        frames.append(page)
        offset += batch

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    log.info("Chicago crime: extracted %s rows", len(df))
    return df


def _download_with_progress(url: str, dest, timeout: int = 60):
    """Stream a file to disk, printing progress, and cache it.

    Reading a remote parquet directly with pandas gives no feedback and no
    timeout, so a stalled connection looks identical to a slow one. Streaming to
    disk fixes both, and caching means a rerun does not re-download 50MB.
    """
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Using cached file at %s (%.1f MB)", dest,
                 dest.stat().st_size / 1e6)
        return dest

    log.info("Downloading %s", url)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    print(f"\r    {done/1e6:6.1f} / {total/1e6:.1f} MB "
                          f"({pct:5.1f}%)", end="", flush=True)
                else:
                    print(f"\r    {done/1e6:6.1f} MB", end="", flush=True)
    print()
    log.info("Saved to %s", dest)
    return dest


def extract_nyc_taxi(sample_rows: int = None) -> pd.DataFrame:
    """Download one month of NYC yellow taxi trips and sample it.

    The monthly files run to millions of rows. We sample rather than truncate
    because taking the first N rows of a file ordered by pickup time would give
    us only the first few days of the month, which skews every day-of-week and
    daily-pattern analysis downstream.
    """
    sample_rows = sample_rows or config.NYC_TAXI_SAMPLE_ROWS
    url = config.NYC_TAXI_URL.format(
        year=config.NYC_TAXI_YEAR, month=config.NYC_TAXI_MONTH
    )
    dest = config.RAW_DIR / f"yellow_tripdata_{config.NYC_TAXI_YEAR}-{config.NYC_TAXI_MONTH:02d}.parquet"

    _download_with_progress(url, dest)

    df = pd.read_parquet(dest)
    log.info("NYC taxi: file contains %s rows", len(df))

    if len(df) > sample_rows:
        df = df.sample(n=sample_rows, random_state=42)   # seeded = reproducible
        log.info("NYC taxi: sampled down to %s rows", len(df))
    return df


def extract_airline_ontime() -> pd.DataFrame:
    """Read the manually downloaded airline on-time CSV.

    BTS serves this behind a form-based download, so there is no stable URL to
    automate against. The README documents the download steps.
    """
    if not config.AIRLINE_CSV.exists():
        raise FileNotFoundError(
            f"Airline CSV not found at {config.AIRLINE_CSV}.\n"
            "Download it from the BTS site (see README) or run with --sample "
            "to build the warehouse from synthetic fixtures instead."
        )
    df = pd.read_csv(config.AIRLINE_CSV, low_memory=False)
    log.info("Airline: extracted %s rows", len(df))
    return df


# ---------------------------------------------------------------------------
# Synthetic fixtures for testing
# ---------------------------------------------------------------------------

def _sample_crime(n: int = 5_000) -> pd.DataFrame:
    """Synthetic data matching the Chicago crime schema, including its flaws.

    Deliberately includes nulls and duplicate case numbers so the cleaning and
    validation steps have something to actually catch. A fixture that is already
    clean tests nothing.
    """
    rng = np.random.default_rng(42)
    types = ["THEFT", "BATTERY", "CRIMINAL DAMAGE", "ASSAULT", "BURGLARY",
             "ROBBERY", "NARCOTICS", "MOTOR VEHICLE THEFT"]
    dates = pd.date_range("2024-01-01", "2024-12-31", freq="h")

    df = pd.DataFrame({
        "case_number": [f"JG{i:06d}" for i in range(n)],
        "date": rng.choice(dates, n),
        "primary_type": rng.choice(types, n),
        "description": rng.choice(["SIMPLE", "OVER $500", "TO VEHICLE",
                                   "FORCIBLE ENTRY", "DOMESTIC"], n),
        "arrest": rng.choice([True, False], n, p=[0.22, 0.78]),
        "domestic": rng.choice([True, False], n, p=[0.17, 0.83]),
        "district": rng.choice([f"{d:03d}" for d in range(1, 26)], n),
    })
    df.loc[df.sample(frac=0.02, random_state=1).index, "district"] = None
    df = pd.concat([df, df.head(50)], ignore_index=True)   # planted duplicates
    return df


def _sample_taxi(n: int = 5_000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    pickups = pd.to_datetime(
        rng.choice(pd.date_range("2024-01-01", "2024-01-31", freq="min"), n)
    )
    distance = np.round(rng.gamma(2.0, 1.6, n), 2)
    fare = np.round(3.0 + distance * 2.8 + rng.normal(0, 1.5, n), 2)

    df = pd.DataFrame({
        "VendorID": rng.choice([1, 2], n),
        "tpep_pickup_datetime": pickups,
        "passenger_count": rng.choice([1, 1, 1, 2, 2, 3, 4, 5], n),
        "trip_distance": distance,
        "fare_amount": fare,
        "tip_amount": np.round(np.clip(fare * rng.uniform(0, 0.3, n), 0, None), 2),
    })
    df["total_amount"] = np.round(df.fare_amount + df.tip_amount + 1.5, 2)
    # Real taxi data contains negative fares from refunds and zero-distance
    # trips. Planting them means the cleaning step gets exercised.
    df.loc[df.sample(frac=0.01, random_state=2).index, "fare_amount"] = -5.0
    df.loc[df.sample(frac=0.01, random_state=3).index, "trip_distance"] = 0.0
    return df


def _sample_airline(n: int = 5_000) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    carriers = {"AA": "American", "DL": "Delta", "UA": "United",
                "WN": "Southwest", "B6": "JetBlue", "AS": "Alaska"}
    airports = ["ORD", "JFK", "LAX", "ATL", "DFW", "DEN", "SFO", "MDW"]
    codes = rng.choice(list(carriers), n)

    dep_delay = np.round(rng.normal(8, 32, n), 0)
    df = pd.DataFrame({
        "FL_DATE": rng.choice(pd.date_range("2024-01-01", "2024-12-31"), n),
        "OP_UNIQUE_CARRIER": codes,
        "CARRIER_NAME": [carriers[c] for c in codes],
        "ORIGIN": rng.choice(airports, n),
        "DEST": rng.choice(airports, n),
        "ORIGIN_CITY_NAME": None,
        "DEP_DELAY": dep_delay,
        "ARR_DELAY": np.round(dep_delay + rng.normal(0, 12, n), 0),
        "CANCELLED": rng.choice([0, 1], n, p=[0.975, 0.025]),
    })
    city_of = {"ORD": "Chicago", "MDW": "Chicago", "JFK": "New York",
               "LAX": "Los Angeles", "ATL": "Atlanta", "DFW": "Dallas",
               "DEN": "Denver", "SFO": "San Francisco"}
    df["ORIGIN_CITY_NAME"] = df["ORIGIN"].map(city_of)
    # Cancelled flights have no delay values - a real pattern worth preserving.
    df.loc[df.CANCELLED == 1, ["DEP_DELAY", "ARR_DELAY"]] = np.nan
    return df


def extract_all(use_sample: bool = False) -> dict[str, pd.DataFrame]:
    """Return the three raw frames, either real or synthetic."""
    if use_sample:
        log.warning("Running with SYNTHETIC fixtures, not real source data")
        return {
            "crime": _sample_crime(),
            "taxi": _sample_taxi(),
            "flight": _sample_airline(),
        }
    return {
        "crime": extract_chicago_crime(),
        "taxi": extract_nyc_taxi(),
        "flight": extract_airline_ontime(),
    }
