import pandas as pd
import sqlite3

conn = sqlite3.connect("../warehouse.db")

df = pd.read_csv("../data/nyc_taxi_sample.csv")

df = df[["tpep_pickup_datetime", "trip_distance", "total_amount"]]
df["tpep_pickup_datetime"] = pd.to_datetime(df["tpep_pickup_datetime"])

# DIM DATE
dim_date = pd.DataFrame()
dim_date["date"] = df["tpep_pickup_datetime"].dt.date
dim_date["year"] = df["tpep_pickup_datetime"].dt.year
dim_date["month"] = df["tpep_pickup_datetime"].dt.month
dim_date["day"] = df["tpep_pickup_datetime"].dt.day
dim_date["weekday"] = df["tpep_pickup_datetime"].dt.day_name()
dim_date["date_key"] = dim_date["date"].astype(str).str.replace("-", "").astype(int)

dim_date.drop_duplicates().to_sql("dim_date", conn, if_exists="append", index=False)

# FACT TRANSPORT
fact = pd.DataFrame()
fact["date_key"] = dim_date["date_key"]
fact["mode_key"] = 2  # Taxi
fact["location_key"] = 3
fact["trips"] = 1
fact["avg_delay"] = 0
fact["distance"] = df["trip_distance"]
fact["revenue"] = df["total_amount"]

fact.to_sql("fact_transport", conn, if_exists="append", index=False)

conn.close()
