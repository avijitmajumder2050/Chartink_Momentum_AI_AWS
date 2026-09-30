"""Upload mutual_funds.json — the Mutual Funds page's data snapshot — to S3
as uploads/mutual_funds.json (same bucket / uploads/ convention as
upload_sector_indices.py). The backend rebuilds this file in S3 every
day (mutual_funds_connector.refresh()), so this script is only for
seeding S3 or a manual override.

Validates the shape first so a typo can't break the live page.

Run:
    python upload_mutual_funds.py
"""

import json
import os
import sys

from connectors import chart_connector
from connectors.mutual_funds_connector import LOCAL_JSON, S3_KEY

FUND_KEYS = ["id", "name", "amc", "category", "aumCr", "expenseRatio", "return1y", "cagr3y", "cagr5y", "risk", "dataDate", "url"]


def validate(data):
    problems = []
    funds = data.get("indexFunds", []) + data.get("equityFunds", [])
    if not funds:
        problems.append("no funds")
    ids = [f.get("id") for f in funds]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        problems.append(f"duplicate fund ids: {sorted(dupes)}")
    for f in funds:
        missing = [k for k in FUND_KEYS if k not in f]
        if missing:
            problems.append(f"{f.get('id', '?')}: missing {missing}")
        for k in ("aumCr", "expenseRatio"):
            if f.get(k) is not None and not isinstance(f.get(k), (int, float)):
                problems.append(f"{f.get('id', '?')}: {k} must be a number or null")
    cats = set(data.get("equityCategories", []))
    stray = {f["category"] for f in data.get("equityFunds", []) if f.get("category") not in cats}
    if stray:
        problems.append(f"equity funds in categories not listed in equityCategories: {sorted(stray)}")
    for ix, etfs in data.get("etfs", {}).items():
        for e in etfs:
            if not e.get("symbol"):
                problems.append(f"ETF under {ix} without a symbol")
    return problems


def main():
    with open(LOCAL_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    problems = validate(data)
    if problems:
        sys.exit("not uploaded — fix these first:\n  " + "\n  ".join(problems))
    client = chart_connector._s3()
    bucket = chart_connector._get_bucket(client)
    # The backend refreshes NAV/returns/ETF prices in S3 daily. Uploading an
    # older local copy over that would roll those numbers back, so require
    # --force unless the local file is at least as fresh.
    try:
        live = json.loads(client.get_object(Bucket=bucket, Key=S3_KEY)["Body"].read())
    except Exception:
        live = {}
    if (live.get("refreshedOn") or "") > (data.get("refreshedOn") or "") and "--force" not in sys.argv:
        sys.exit(
            f"not uploaded — S3 was refreshed on {live['refreshedOn']}, newer than this file "
            f"({data.get('refreshedOn') or 'never refreshed'}). Start from the current S3 copy "
            f"(aws s3 cp s3://{bucket}/{S3_KEY} mutual_funds.json), edit, then upload — or pass --force."
        )
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    client.put_object(Bucket=bucket, Key=S3_KEY, Body=body, ContentType="application/json; charset=utf-8")
    print(
        f"uploaded {len(data['indexFunds'])} index funds, {len(data['equityFunds'])} equity funds, "
        f"{sum(len(v) for v in data['etfs'].values())} ETFs to s3://{bucket}/{S3_KEY}"
    )


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
