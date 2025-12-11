import pandas as pd
import sqlite3

conn = sqlite3.connect("../warehouse.db")

df = pd.read_csv("../data/chicago_crime_sample.csv")

df = df[["Date", "Primary Type", "Latitude", "Longitude"]]

df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

# DIM DATE TABLE
dim_date = pd.DataFrame()
dim_date["date"] = df["Date"].dt.date
dim_date["year"] = df["Date"].dt.year
dim_date["month"] = df["Date"].dt.month
dim_date["day"] = df["Date"].dt.day
dim_date["weekday"] = df["Date"].dt.day_name()
dim_date["date_key"] = dim_date["date"].astype(str).str.replace("-", "").astype(int)

dim_date.drop_duplicates().to_sql("dim_date", conn, if_exists="append", index=False)

# DIM LOCATION TABLE
dim_location = df[["Latitude", "Longitude"]].drop_duplicates()
dim_location["city"] = "Chicago"
dim_location["state"] = "IL"
dim_location["location_key"] = dim_location.index + 1

dim_location.to_sql("dim_location", conn, if_exists="append", index=False)

# FACT TABLE
fact = pd.DataFrame()
fact["date_key"] = df["Date"].dt.date.astype(str).str.replace("-", "").astype(int)
fact["location_key"] = 1
fact["crime_type"] = df["Primary Type"]

fact.to_sql("fact_crime", conn, if_exists="append", index=False)

conn.close()
