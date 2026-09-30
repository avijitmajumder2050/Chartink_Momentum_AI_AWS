"""Mutual Funds page data — a hand-collected snapshot (index funds, top
equity funds per SEBI category, index -> ETF lookup), kept as JSON in S3
at uploads/mutual_funds.json so the figures can be refreshed without a
deploy (upload_mutual_funds.py). The copy bundled in the repo is the
fallback if S3 is unreachable.

Not live data: the file itself says when each figure was collected, and
the page shows that. The first version was extracted verbatim from the
"MarketPulse Fund Watchlist" artifact (figures collected 30 Sep 2026).
"""

import json
import os

from connectors import cache, chart_connector

S3_KEY = "uploads/mutual_funds.json"
LOCAL_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mutual_funds.json")
CACHE_TTL_SECONDS = 60 * 60


def _fetch():
    try:
        client = chart_connector._s3()
        bucket = chart_connector._get_bucket(client)
        data = json.loads(client.get_object(Bucket=bucket, Key=S3_KEY)["Body"].read())
        source = "s3"
    except Exception:
        with open(LOCAL_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
        source = "bundled"
    data["source"] = source
    return data


def get_mutual_funds():
    return cache.get_or_fetch("mutual_funds_snapshot", CACHE_TTL_SECONDS, _fetch)
