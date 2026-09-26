"""Build sector_constituents.csv — which stocks make up each sector index —
from NSE's own published index lists, and upload it to S3 as
uploads/sector_constituents.csv (same bucket/convention as
upload_sector_indices.py).

Source: for every row in sector_indices.csv with an nse_constituents_file,
https://archives.nseindia.com/content/indices/<that file>. NSE rebalances
these twice a year (March / September), so re-run this after a
rebalance. It runs from here rather than on the server because NSE
blocks some cloud IPs; the server only ever reads the S3 copy
(connectors/sector_connector.py), with the repo copy as a fallback.

Output columns: index_symbol, stock_symbol, company_name, industry

Run:
    python upload_sector_constituents.py
"""

import io
import os
import sys
import time

import pandas as pd
import requests

from connectors import chart_connector
from connectors.sector_connector import CONSTITUENTS_LOCAL_CSV, CONSTITUENTS_S3_KEY, LOCAL_CSV

NSE_INDICES_BASE = "https://archives.nseindia.com/content/indices/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def fetch_list(filename):
    for attempt in range(3):
        try:
            resp = requests.get(NSE_INDICES_BASE + filename, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            df = pd.read_csv(io.BytesIO(resp.content))
            return df[["Symbol", "Company Name", "Industry"]]
        except Exception as exc:
            last = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"{filename}: {last}")


def main():
    indices = pd.read_csv(LOCAL_CSV).fillna({"nse_constituents_file": ""})
    wanted = indices[indices["nse_constituents_file"].astype(str).str.strip() != ""]
    frames, failed = [], []
    for row in wanted.itertuples():
        try:
            lst = fetch_list(row.nse_constituents_file.strip())
        except Exception as exc:
            failed.append(str(exc))
            continue
        frames.append(pd.DataFrame({
            "index_symbol": row.symbol,
            "stock_symbol": lst["Symbol"].astype(str).str.strip().str.upper(),
            "company_name": lst["Company Name"].astype(str).str.strip(),
            "industry": lst["Industry"].astype(str).str.strip(),
        }))
        print(f"  {row.symbol:18} {len(lst):3} stocks")
    if failed:
        # Never upload a partial file over a good one.
        sys.exit("aborting, nothing uploaded — failed: " + "; ".join(failed))

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(CONSTITUENTS_LOCAL_CSV, index=False, lineterminator="\n")
    client = chart_connector._s3()
    bucket = chart_connector._get_bucket(client)
    client.put_object(Bucket=bucket, Key=CONSTITUENTS_S3_KEY, Body=out.to_csv(index=False).encode("utf-8"), ContentType="text/csv")
    print(f"uploaded {len(out)} rows ({out['stock_symbol'].nunique()} unique stocks, {len(frames)} sectors) to s3://{bucket}/{CONSTITUENTS_S3_KEY}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
