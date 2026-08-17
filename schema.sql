-- ---------------------------------------------------------------------------
-- BI Data Warehouse - star schema DDL
--
-- Three fact tables sharing conformed dimensions. The design decision that
-- matters most here: dim_date and dim_location are CONFORMED, meaning the same
-- dimension row is referenced by facts from different source systems. That is
-- what makes cross-source analysis possible - you can ask "what happened in
-- this area on this date" across crime, taxi and flight data using one join
-- path instead of three incompatible ones.
--
-- All dimensions are Type 1 (overwrite on change). None of these sources carry
-- history that needs preserving, so Type 2 slowly-changing dimensions would add
-- complexity with no analytical benefit.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS fact_crime;
DROP TABLE IF EXISTS fact_taxi_trip;
DROP TABLE IF EXISTS fact_flight;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_location;
DROP TABLE IF EXISTS dim_crime_type;
DROP TABLE IF EXISTS dim_carrier;
DROP TABLE IF EXISTS dim_vendor;

-- ---------------------------------------------------------------------------
-- CONFORMED DIMENSIONS
-- ---------------------------------------------------------------------------

-- Grain: one row per calendar day.
-- Generated for a fixed range rather than derived from the facts, so days with
-- no activity still exist and show as zero rather than vanishing from reports.
CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,   -- YYYYMMDD, a readable surrogate key
    full_date       TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT    NOT NULL,
    day             INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,      -- 0 = Monday
    day_name        TEXT    NOT NULL,
    week_of_year    INTEGER NOT NULL,
    is_weekend      INTEGER NOT NULL       -- 0/1; SQLite has no boolean type
);

-- Grain: one row per city.
-- City is the coarsest common level across all three sources, and conforming
-- requires the level they all share. Chicago crime has block-level detail and
-- taxi has zone-level detail, but flights only resolve to airport city - so
-- city is the join level. Finer geography stays as degenerate attributes on
-- the fact rows where it exists.
CREATE TABLE dim_location (
    location_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    city            TEXT    NOT NULL,
    state           TEXT,
    country         TEXT    DEFAULT 'USA',
    UNIQUE (city, state)
);

-- ---------------------------------------------------------------------------
-- SOURCE-SPECIFIC DIMENSIONS
-- ---------------------------------------------------------------------------

CREATE TABLE dim_crime_type (
    crime_type_key  INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_type    TEXT    NOT NULL,
    description     TEXT,
    is_violent      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (primary_type, description)
);

CREATE TABLE dim_carrier (
    carrier_key     INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_code    TEXT    NOT NULL UNIQUE,
    carrier_name    TEXT
);

CREATE TABLE dim_vendor (
    vendor_key      INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       INTEGER NOT NULL UNIQUE,
    vendor_name     TEXT
);

-- ---------------------------------------------------------------------------
-- FACT TABLES
-- ---------------------------------------------------------------------------

-- Grain: one row per reported crime incident.
-- case_number is a degenerate dimension - a natural key kept on the fact row
-- because it identifies the incident but has no attributes worth a dimension.
CREATE TABLE fact_crime (
    crime_sk        INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    location_key    INTEGER NOT NULL REFERENCES dim_location(location_key),
    crime_type_key  INTEGER NOT NULL REFERENCES dim_crime_type(crime_type_key),
    case_number     TEXT,
    district        TEXT,
    arrest_made     INTEGER NOT NULL DEFAULT 0,
    domestic        INTEGER NOT NULL DEFAULT 0,
    incident_count  INTEGER NOT NULL DEFAULT 1   -- additive measure
);

-- Grain: one row per completed taxi trip.
CREATE TABLE fact_taxi_trip (
    trip_sk         INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    location_key    INTEGER NOT NULL REFERENCES dim_location(location_key),
    vendor_key      INTEGER NOT NULL REFERENCES dim_vendor(vendor_key),
    pickup_hour     INTEGER,
    passenger_count INTEGER,
    trip_distance   REAL,
    fare_amount     REAL,
    tip_amount      REAL,
    total_amount    REAL,
    trip_count      INTEGER NOT NULL DEFAULT 1
);

-- Grain: one row per scheduled flight.
-- Note dep_delay_minutes is additive but arr_delay is only meaningful averaged,
-- which is why both are stored raw and aggregation is left to the query layer.
CREATE TABLE fact_flight (
    flight_sk       INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    location_key    INTEGER NOT NULL REFERENCES dim_location(location_key),
    carrier_key     INTEGER NOT NULL REFERENCES dim_carrier(carrier_key),
    origin_airport  TEXT,
    dest_airport    TEXT,
    dep_delay_min   REAL,
    arr_delay_min   REAL,
    cancelled       INTEGER NOT NULL DEFAULT 0,
    flight_count    INTEGER NOT NULL DEFAULT 1
);

-- ---------------------------------------------------------------------------
-- INDEXES
-- Foreign keys are the join paths every query uses. Without these, SQLite scans
-- the whole fact table for each join.
-- ---------------------------------------------------------------------------
CREATE INDEX idx_crime_date     ON fact_crime(date_key);
CREATE INDEX idx_crime_location ON fact_crime(location_key);
CREATE INDEX idx_crime_type     ON fact_crime(crime_type_key);
CREATE INDEX idx_taxi_date      ON fact_taxi_trip(date_key);
CREATE INDEX idx_taxi_location  ON fact_taxi_trip(location_key);
CREATE INDEX idx_flight_date    ON fact_flight(date_key);
CREATE INDEX idx_flight_carrier ON fact_flight(carrier_key);
