-- ---------------------------------------------------------------------------
-- Analysis queries
--
-- These exist to demonstrate what the conformed dimensions actually buy you.
-- Queries 5 and 6 are the point of the whole project: they join facts from
-- different source systems through the shared date dimension, which is not
-- possible against the raw files.
-- ---------------------------------------------------------------------------

-- 1. Crime volume by month and type, with arrest rate
SELECT
    d.year,
    d.month_name,
    ct.primary_type,
    SUM(f.incident_count)                              AS incidents,
    SUM(f.arrest_made)                                 AS arrests,
    ROUND(100.0 * SUM(f.arrest_made) / SUM(f.incident_count), 1) AS arrest_rate_pct
FROM fact_crime f
JOIN dim_date d       ON f.date_key = d.date_key
JOIN dim_crime_type ct ON f.crime_type_key = ct.crime_type_key
GROUP BY d.year, d.month, ct.primary_type
ORDER BY d.year, d.month, incidents DESC;


-- 2. Violent vs non-violent crime split by day of week
-- Uses the is_violent flag built in the dimension rather than repeating the
-- category list in every query. Classification logic lives in one place.
SELECT
    d.day_name,
    SUM(CASE WHEN ct.is_violent = 1 THEN 1 ELSE 0 END) AS violent,
    SUM(CASE WHEN ct.is_violent = 0 THEN 1 ELSE 0 END) AS non_violent,
    COUNT(*)                                           AS total
FROM fact_crime f
JOIN dim_date d        ON f.date_key = d.date_key
JOIN dim_crime_type ct ON f.crime_type_key = ct.crime_type_key
GROUP BY d.day_of_week, d.day_name
ORDER BY d.day_of_week;


-- 3. Taxi revenue and tipping by hour of day
SELECT
    f.pickup_hour,
    COUNT(*)                        AS trips,
    ROUND(AVG(f.trip_distance), 2)  AS avg_distance_mi,
    ROUND(AVG(f.fare_amount), 2)    AS avg_fare,
    ROUND(100.0 * SUM(f.tip_amount) / SUM(f.fare_amount), 1) AS tip_pct_of_fare
FROM fact_taxi_trip f
GROUP BY f.pickup_hour
ORDER BY f.pickup_hour;


-- 4. Carrier on-time performance
-- Cancelled flights are excluded from delay averages but counted separately,
-- because averaging a delay over flights that never departed is meaningless.
SELECT
    c.carrier_code,
    c.carrier_name,
    COUNT(*)                                                     AS flights,
    SUM(f.cancelled)                                             AS cancellations,
    ROUND(100.0 * SUM(f.cancelled) / COUNT(*), 2)                AS cancel_rate_pct,
    ROUND(AVG(CASE WHEN f.cancelled = 0 THEN f.dep_delay_min END), 1) AS avg_dep_delay_min,
    ROUND(100.0 * SUM(CASE WHEN f.cancelled = 0 AND f.arr_delay_min <= 15 THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN f.cancelled = 0 THEN 1 ELSE 0 END), 0), 1) AS on_time_pct
FROM fact_flight f
JOIN dim_carrier c ON f.carrier_key = c.carrier_key
GROUP BY c.carrier_key
ORDER BY on_time_pct DESC;


-- 5. CROSS-SOURCE: daily activity across all three sources
-- This is what the conformed date dimension makes possible. dim_date is the shared spine and
-- each source contributes its own measure against the same calendar.
-- Days with no activity in a source return 0 rather than disappearing, because
-- the dimension was generated for the full range rather than derived from facts.
SELECT
    d.full_date,
    d.day_name,
    d.is_weekend,
    COALESCE(cr.incidents, 0)   AS crime_incidents,
    COALESCE(tx.trips, 0)       AS taxi_trips,
    COALESCE(fl.flights, 0)     AS flights,
    COALESCE(fl.cancellations, 0) AS flight_cancellations
FROM dim_date d
LEFT JOIN (SELECT date_key, COUNT(*) AS incidents FROM fact_crime GROUP BY date_key) cr
       ON d.date_key = cr.date_key
LEFT JOIN (SELECT date_key, COUNT(*) AS trips FROM fact_taxi_trip GROUP BY date_key) tx
       ON d.date_key = tx.date_key
LEFT JOIN (SELECT date_key, COUNT(*) AS flights, SUM(cancelled) AS cancellations
           FROM fact_flight GROUP BY date_key) fl
       ON d.date_key = fl.date_key
WHERE cr.incidents IS NOT NULL OR tx.trips IS NOT NULL OR fl.flights IS NOT NULL
ORDER BY d.full_date;


-- 6. CROSS-SOURCE: weekend vs weekday behaviour across every source
-- One question, answered against three unrelated source systems at once.
SELECT
    CASE WHEN d.is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    ROUND(AVG(cr.incidents), 1)  AS avg_daily_crime,
    ROUND(AVG(tx.trips), 1)      AS avg_daily_taxi_trips,
    ROUND(AVG(fl.flights), 1)    AS avg_daily_flights
FROM dim_date d
LEFT JOIN (SELECT date_key, COUNT(*) AS incidents FROM fact_crime GROUP BY date_key) cr
       ON d.date_key = cr.date_key
LEFT JOIN (SELECT date_key, COUNT(*) AS trips FROM fact_taxi_trip GROUP BY date_key) tx
       ON d.date_key = tx.date_key
LEFT JOIN (SELECT date_key, COUNT(*) AS flights FROM fact_flight GROUP BY date_key) fl
       ON d.date_key = fl.date_key
WHERE cr.incidents IS NOT NULL OR tx.trips IS NOT NULL OR fl.flights IS NOT NULL
GROUP BY d.is_weekend;
