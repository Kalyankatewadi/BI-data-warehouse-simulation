import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import extract

df = extract.extract_chicago_crime(limit=50_000)
print("raw 'date' sample:", df["date"].head(3).tolist())

parsed = pd.to_datetime(df["date"], errors="coerce", format="mixed")
print("\nparsed min :", parsed.min())
print("parsed max :", parsed.max())
print("unparseable:", parsed.isna().sum())
print("\nrows per year:")
print(parsed.dt.year.value_counts().sort_index().to_string())