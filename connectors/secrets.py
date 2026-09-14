"""Secrets from AWS SSM Parameter Store, with a short in-memory cache.

Never persisted to disk — connectors/cache.py's file-based cache is for
scraped market data, not credentials. Uses boto3's default credential
chain, so it picks up whatever AWS_PROFILE / instance role / env
credentials are already configured — no profile name is hardcoded here.
"""

import os
import time

try:
    import boto3
except ImportError:
    boto3 = None

_cache = {}  # name -> (value, fetched_at)
_TTL_SECONDS = 15 * 60


def get_parameter(name, region=None):
    if boto3 is None:
        raise RuntimeError("boto3 is not installed")

    now = time.time()
    cached = _cache.get(name)
    if cached and (now - cached[1]) < _TTL_SECONDS:
        return cached[0]

    client = boto3.client(
        "ssm",
        region_name=region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
    )
    response = client.get_parameter(Name=name, WithDecryption=True)
    value = response["Parameter"]["Value"]
    _cache[name] = (value, now)
    return value
