BI Data Warehouse Project
Integrates three real-world public datasets into a single business intelligence data warehouse using SQLite, modeled as a star schema and ready to connect to Power BI or Tableau.

Datasets: Chicago Crime, US Airline Delays, NYC Taxi Trips


What it does
These three datasets are published independently and cannot be joined as-is. They use different date formats, different geography keys, and different grains, and they share no identifiers. This project builds the warehouse layer that makes them queryable together: conformed date and location dimensions, fact tables at a declared grain, and a Python ETL process that loads them consistently.

The result is a single database file that a BI tool can point at directly.
Data sources
Dataset
Grain
Rows
Chicago Crime
One row per reported incident
TODO
US Airline Delays
One row per scheduled flight
TODO
NYC Taxi Trips
One row per completed trip
TODO


TODO: add source links for each dataset.
Approach
1. Profiling

Each source was checked for null rates, duplicates, out-of-range values, and inconsistent categorical encoding before any modeling decisions were made.

2. Star schema design

Dimensions are conformed where the sources overlap, so the same dimension serves more than one fact table:

dim_date shared across all three sources
dim_location rolled up to a level the sources have in common
Source-specific dimensions for carrier, crime type, and vendor
Fact tables at the declared grain, with measures kept additive where possible

3. Python ETL

Extract, transform, and load scripts handle type coercion, date parsing, surrogate key assignment, and referential checks against the dimensions before facts are loaded.

4. Validation

Row counts are reconciled between source and target, foreign keys are checked for orphans, and null rates on required columns are tested against thresholds. A failed check stops the load rather than letting rows drop silently.
Tech stack
Python, SQLite, SQL, pandas, star schema modeling, Power BI / Tableau
Project structure
TODO: paste your actual folder structure here
Running
git clone https://github.com/Kalyankatewadi/BI-data-warehouse-simulation.git

cd BI-data-warehouse-simulation

pip install -r requirements.txt

python build_warehouse.py

TODO: correct the script name to match your repo.

The build produces a SQLite database file. Connect Power BI or Tableau directly to it, or query it with any SQL client.
What this demonstrates
Declaring grain before modeling rather than loading raw and sorting it out later
Conformed dimensions that give unrelated sources a shared query surface
Data quality checks built into the load process
SQL and dimensional modeling applied to messy public data rather than a clean sample set
Scale
TODO: add total rows loaded, number of dimensions and fact tables, and end-to-end build time.
Notes and limitations
SQLite was chosen so the project runs anywhere with no infrastructure setup. The same model moves to Snowflake, Postgres, or BigQuery without redesign; only the DDL dialect and load mechanics change. Geography is rolled up to a coarse common level to conform across sources, which limits how granular cross-dataset location analysis can go.



Kalyan Katewadi · Portfolio · LinkedIn

