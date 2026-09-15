"""Tiny file-based TTL cache so connectors don't re-scrape on every page
load. Falls back to stale cache (rather than raising) whenever the fetch
function itself fails, so a broken upstream site degrades gracefully
instead of taking the cache down with it.
"""

import json
import os
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")


def _path(key):
    safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return os.path.join(CACHE_DIR, f"{safe_key}.json")


def _read(key):
    path = _path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write(key, value):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _path(key)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"cached_at": time.time(), "data": value}, fh, ensure_ascii=False)


def get_or_fetch(key, ttl_seconds, fetch_fn, force=False):
    """Return cached data for `key` if it's younger than `ttl_seconds`,
    otherwise call `fetch_fn()`, cache the result, and return it.

    If `fetch_fn()` raises, any existing cache entry (even stale) is
    returned instead; only re-raises if there's no cache at all.

    `force=True` skips the freshness check and always re-fetches — for a
    caller that represents an explicit "do this now" user action (e.g. a
    scanner's Run button) rather than a passive read, where silently
    handing back a same-looking cached result with no fresh work done
    would be confusing, not helpful. Still writes the fresh result to
    cache, so a subsequent non-forced read (e.g. the same scanner's
    "last cached result" view) reflects it.
    """
    entry = _read(key)

    if not force and entry is not None and (time.time() - entry["cached_at"]) < ttl_seconds:
        return entry["data"]

    try:
        fresh = fetch_fn()
    except Exception:
        if entry is not None:
            return entry["data"]
        raise

    _write(key, fresh)
    return fresh


def peek(key):
    """Return the raw {cached_at, data} entry for `key`, or None if nothing
    is cached yet — for rendering a last-known result without triggering
    fetch_fn (e.g. showing a scanner's last run when it's selected, without
    kicking off a fresh live run)."""
    return _read(key)
