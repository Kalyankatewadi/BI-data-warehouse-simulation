# BI Data Warehouse

A dimensional data warehouse that integrates three unrelated public datasets into one SQLite database, modeled as a star schema with conformed dimensions.

**Datasets:** Chicago Crime, NYC Yellow Taxi Trips, US Airline On-Time Performance

\---

## The problem

These three datasets are published independently and cannot be analyzed together as they ship. They use different date formats, different geography levels, different grains, and share no identifiers. Answering something as simple as "does activity differ on weekends across all three" requires reconciling them first.

This project builds that reconciliation layer: conformed date and location dimensions, fact tables at a declared grain, and an ETL process with data quality checks that fail the build rather than loading bad data.

## Design decisions

**Star schema over normalized tables.** Analytical queries join a fact to a handful of dimensions and aggregate. A snowflake or third-normal-form design would add joins to every query for storage savings that do not matter at this scale.

**Conformed dimensions.** `dim\_date` and `dim\_location` are shared across all three fact tables. This is the decision that makes cross-source analysis possible at all — one join path instead of three incompatible ones.

**City as the location grain.** Conforming requires the coarsest level all sources share. Crime data resolves to block, taxi to zone, flights only to airport city. City is therefore the join level, and finer geography stays as degenerate attributes on the facts that have it.

**Generated date dimension.** `dim\_date` is generated for a fixed range rather than derived from observed dates. A day with no activity still exists and reports as zero instead of disappearing from the result set.

**Type 1 dimensions.** None of these sources carry history that needs preserving, so slowly-changing dimension tracking would add complexity with no analytical payoff.

**Full rebuild rather than incremental load.** The schema is dropped and recreated each run, so the build is idempotent and takes seconds. Incremental loading would be the right call at production volume; it is not at this one.

## Pipeline

```
extract  →  transform  →  load  →  validate
```

**Extract.** Chicago crime comes from the Socrata API with paging. Taxi data is a monthly parquet file, sampled with a fixed seed after download — sampling rather than truncating, because the file is ordered by pickup time and taking the first N rows would give only the first days of the month.

**Transform.** Every source is profiled for null rates, duplicates and range violations before any cleaning rule is written. Dimensions are built and assigned surrogate keys first, then facts join against them to pick up those keys. A fact row whose dimension lookup fails is dropped and counted, never loaded with a null key.

**Load.** Dimensions load before facts. Foreign key enforcement is switched on explicitly, since SQLite disables it by default.

**Validate.** Four check families run against the loaded database: row counts, orphan foreign keys, null rates on required columns, and measure sanity including business-rule contradictions such as a cancelled flight carrying a delay value. Any failure raises and aborts the build.

## Tech stack

Python, SQLite, SQL, pandas, pyarrow

## Project structure

```
├── build\_warehouse.py      orchestrator
├── config.py               paths, sources, thresholds
├── requirements.txt
├── src/
│   ├── schema.sql          star schema DDL
│   ├── extract.py          source extraction and test fixtures
│   ├── transform.py        profiling, cleaning, dimension and fact builds
│   ├── load.py             schema creation and loading
│   └── validate.py         data quality checks
├── queries/
│   └── analysis.sql        six analysis queries, two of them cross-source
└── data/
    ├── raw/                downloaded source files
    └── warehouse/          the built SQLite database
```

## Running it

```bash
git clone https://github.com/Kalyankatewadi/BI-data-warehouse-simulation.git
cd BI-data-warehouse-simulation
pip install -r requirements.txt
```

Build against synthetic fixtures, which requires no downloads and takes under a second:

```bash
python build\_warehouse.py --sample
```

Build against real source data:

```bash
python build\_warehouse.py
```

Chicago crime and taxi data download automatically. Airline on-time performance has no clean public API — download it from the BTS site, save it as `data/raw/airline\_ontime.csv`, and rerun.

Then query it:

```bash
sqlite3 data/warehouse/bi\_warehouse.db < queries/analysis.sql
```

Or connect Power BI or Tableau directly to the database file.

## Test fixtures

`--sample` generates synthetic data matching each source's real schema, including planted duplicate case numbers, negative fares and zero-distance trips. The fixtures are deliberately dirty so the cleaning and validation steps have something to catch — a fixture that is already clean tests nothing.

Fixture data is for testing the pipeline only and is never presented as real analysis.

## Results

TODO: run the real build and paste the summary output here...



TODO: add one finding from queries 5 or 6...

## Limitations

SQLite was chosen so the project runs anywhere with no infrastructure. The model moves to Snowflake, Postgres or BigQuery without redesign; only the DDL dialect and load mechanics change.

Conforming location to city level means cross-source geographic analysis cannot go finer than city, even though two of the three sources carry more detail.

Correlation across these sources is coincidental. Crime, taxi and flight activity share a calendar, not a causal relationship. The warehouse makes the comparison possible; it does not make it meaningful, and any finding should be read as descriptive.

\---

**Kalyan Katewadi** · [Portfolio](https://kalyankatewadi.github.io) · [LinkedIn](https://www.linkedin.com/in/kalyan-katewadi/)

