"""
Central configuration for the BI data warehouse build.

Everything that might change between environments lives here rather than being
scattered through the ETL modules. If you point this at different files or want
a different sample size, this is the only file you edit.
"""

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
DB_PATH = WAREHOUSE_DIR / "bi_warehouse.db"
SCHEMA_PATH = PROJECT_ROOT / "src" / "schema.sql"

for directory in (RAW_DIR, WAREHOUSE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Source data
# --------------------------------------------------------------------------
# Chicago Crime is served by the Socrata Open Data API, which supports paging
# and a $limit parameter. We cap the pull rather than taking all 8M+ rows,
# because the point of this project is the modelling, not the volume.
CHICAGO_CRIME_API = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
CHICAGO_CRIME_LIMIT = 50_000

# Socrata returns rows in no meaningful order - an unfiltered pull spans 2001 to
# the present, with most rows from the early 2000s. The other two sources are
# both January 2024, so crime is filtered to the same window. Without this the
# cross-source queries have almost no overlapping dates to join on, which defeats
# the purpose of the conformed date dimension.
ANALYSIS_START = "2024-01-01"
ANALYSIS_END = "2024-12-31"

# NYC TLC publishes monthly parquet files at stable URLs.
NYC_TAXI_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "yellow_tripdata_{year}-{month:02d}.parquet"
)
NYC_TAXI_YEAR = 2024
NYC_TAXI_MONTH = 1
NYC_TAXI_SAMPLE_ROWS = 50_000  # taxi files are large; we sample after download

# Airline on-time performance has no clean public API. Download the CSV
# manually (instructions in the README) and drop it at this path.
AIRLINE_CSV = RAW_DIR / "airline_ontime.csv"

# --------------------------------------------------------------------------
# Date dimension range
# --------------------------------------------------------------------------
# dim_date is generated rather than derived from the sources. Generating it
# means every date in range exists even if no fact row references it, which is
# what lets you report on a day that had zero activity. Deriving the dimension
# from observed dates would silently drop those days.
# The range must cover every date present in the sources. Too narrow and facts
# get dropped as orphans - the Chicago Socrata API returns the most recent
# incidents, so the end date has to stay ahead of today, not behind it.
DATE_DIM_START = "2023-01-01"
DATE_DIM_END = "2025-12-31"

# --------------------------------------------------------------------------
# Data quality thresholds
# --------------------------------------------------------------------------
# Loads fail if these are breached. Failing loudly beats loading bad data and
# discovering it in a dashboard three weeks later.
MAX_NULL_RATE = 0.05          # max share of nulls allowed in a required column
MAX_ORPHAN_RATE = 0.0         # no fact row may reference a missing dimension
MIN_ROWS_PER_FACT = 100       # a fact table below this means something broke
MAX_DROP_RATE = 0.05          # max share of source rows a fact may discard
