-- DIMENSION TABLES

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    date TEXT,
    year INTEGER,
    month INTEGER,
    day INTEGER,
    weekday TEXT
);

CREATE TABLE dim_location (
    location_key INTEGER PRIMARY KEY,
    city TEXT,
    state TEXT,
    latitude REAL,
    longitude REAL
);

CREATE TABLE dim_transport_mode (
    mode_key INTEGER PRIMARY KEY,
    mode TEXT
);

-- FACT TABLES

CREATE TABLE fact_crime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key INTEGER,
    location_key INTEGER,
    crime_type TEXT,
    FOREIGN KEY(date_key) REFERENCES dim_date(date_key),
    FOREIGN KEY(location_key) REFERENCES dim_location(location_key)
);

CREATE TABLE fact_transport (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key INTEGER,
    mode_key INTEGER,
    location_key INTEGER,
    trips INTEGER,
    avg_delay REAL,
    distance REAL,
    revenue REAL,
    FOREIGN KEY(date_key) REFERENCES dim_date(date_key),
    FOREIGN KEY(location_key) REFERENCES dim_location(location_key),
    FOREIGN KEY(mode_key) REFERENCES dim_transport_mode(mode_key)
);
