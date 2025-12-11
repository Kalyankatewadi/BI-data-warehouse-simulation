import pandas as pd
import sqlite3

conn = sqlite3.connect("../warehouse.db")

df = pd.read_csv("../data/airline_on_time_sample.csv")

df = df[["FL_DATE", "ORIGIN", "DEP_DELAY", "DISTANCE"]]
df["FL_DATE"] = pd.to_datetime(df["FL_DATE"])

# DIM DATE
dim_date = pd.DataFrame()
dim_date["date"] = df["FL_DATE"].dt.date
dim_date["year"] = df["FL_DATE"].dt.year
dim_date["month"] = df["FL_DATE"].dt.month
dim_date["day"] = df["FL_DATE"].dt.day
dim_date["weekday"] = df["FL_DATE"].dt.day_name()
dim_date["date_key"] = dim_date["date"].astype(str).str.replace("-", "").astype(int)

dim_date.drop_duplicates().to_sql("dim_date", conn, if_exists="append", index=False)

# FACT TRANSPORT
fact = pd.DataFrame()
fact["date_key"] = dim_date["date_key"]
fact["mode_key"] = 1  # Airline
fact["location_key"] = 2
fact["trips"] = 1
fact["avg_delay"] = df["DEP_DELAY"]
fact["distance"] = df["DISTANCE"]
fact["revenue"] = df["DISTANCE"] * 0.35  # dummy model

fact.to_sql("fact_transport", conn, if_exists="append", index=False)

conn.close()
