"""Upload sector_indices.csv — the Sector Overview page's tracked index
list — to S3 as uploads/sector_indices.csv, in the same bucket and
uploads/ convention as upload_security_master.py.

connectors/sector_connector.py reads it from S3 (cached for an hour), so
editing the list is: change sector_indices.csv, run this script. No
deploy needed. The copy in the repo is also the fallback if S3 is down.

Columns:
  security_id   Dhan index security id (IDX_I segment) — from Dhan's
                scrip master / index_watchlist.csv
  symbol        Dhan's symbol name for the index
  display_name  name shown on the page
  category      Broad market | Sector | Thematic | Strategy | Volatility | Derivative
  investable    true -> the 200 EMA / RSI eligibility rule applies
  track         false -> not shown at all
  sort_order    display order

Run:
    python upload_sector_indices.py
"""

import os
import sys

import pandas as pd

from connectors import chart_connector
from connectors.sector_connector import LOCAL_CSV, S3_KEY

REQUIRED_COLUMNS = ["security_id", "symbol", "display_name", "category", "investable", "track", "sort_order"]


def main():
    df = pd.read_csv(LOCAL_CSV)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"{LOCAL_CSV} is missing columns: {missing}")
    if df["security_id"].duplicated().any():
        sys.exit(f"duplicate security_id values: {df.loc[df['security_id'].duplicated(), 'security_id'].tolist()}")

    client = chart_connector._s3()
    bucket = chart_connector._get_bucket(client)
    with open(LOCAL_CSV, "rb") as fh:
        client.put_object(Bucket=bucket, Key=S3_KEY, Body=fh.read(), ContentType="text/csv")
    print(f"uploaded {len(df)} indices ({int(df['track'].astype(str).str.lower().eq('true').sum())} tracked) "
          f"to s3://{bucket}/{S3_KEY}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
