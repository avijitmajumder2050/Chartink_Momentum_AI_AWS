"""Monthly refresh of Dhan's public NSE security master CSV into S3
(new-dhan-trading-data/uploads/dhan_security_master.csv).

Why: connectors/chart_connector.py and connectors/dhan_connector.py both
fetch this file straight from Dhan's CDN (images.dhan.co) on every cache
miss. Keeping a copy in the same S3 bucket the project's other uploads/*
files already live in means a stale/unreachable CDN doesn't take the
symbol-resolution fallback down with it, and gives other tools in this
account a local copy to read without hitting Dhan at all.

This uploads the file as-is (unfiltered — every exchange/segment Dhan
publishes, not just NSE equity) so it stays useful beyond what this
project's own NSE-equity filtering needs today. The filename is stable
(no date in the key) since callers want "the current one", the same
convention uploads/mapping.csv already uses in this bucket — each run
overwrites the last.

Run manually:
    python upload_security_master.py

Schedule monthly:
  Windows Task Scheduler — create a monthly trigger that runs:
    <path to venv>\\Scripts\\python.exe <path to this file>
  cron (Linux/EC2), 03:00 on the 1st of each month:
    0 3 1 * * /path/to/venv/bin/python /path/to/upload_security_master.py
"""

import datetime
import io
import logging

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
AWS_REGION = "ap-south-1"
BUCKET = "new-dhan-trading-data"
S3_KEY = "uploads/dhan_security_master.csv"


def upload_security_master():
    logger.info("Fetching Dhan security master from %s", SCRIP_MASTER_URL)
    response = requests.get(SCRIP_MASTER_URL, timeout=30)
    response.raise_for_status()
    content = response.content
    logger.info("Downloaded %.1f KB", len(content) / 1024)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError as exc:
        raise RuntimeError(f"S3 bucket {BUCKET!r} is not accessible: {exc}") from exc

    s3.put_object(
        Bucket=BUCKET,
        Key=S3_KEY,
        Body=content,
        ContentType="text/csv",
        Metadata={"uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
    )
    logger.info("Uploaded to s3://%s/%s", BUCKET, S3_KEY)


if __name__ == "__main__":
    upload_security_master()
