"""Sector overview — NSE sector/broad/thematic indices with a simple
"investment eligible" screen.

The tracked list is sector_indices.csv, kept in S3 at
uploads/sector_indices.csv (same bucket and uploads/ convention as the
security master; see upload_sector_indices.py) so it can be edited
without a deploy and reused by other tools. The copy bundled in the repo
is the fallback if S3 is unreachable.

Eligibility rule (per index, on daily closes):
  * price condition: close below its 200-day EMA, or within
    NEAR_EMA_PCT (1%) above it  -> distance from EMA <= +1%
  * RSI condition:   daily RSI(14) below RSI_MAX (35)
  * eligible = investable AND both conditions.

History: ~3 years of daily bars per index, fetched directly rather than
via chart_connector.get_ohlcv(), which keeps only ~200 bars — too few for
a meaningful 200-day EMA. Today's live bar is merged on top from
chart_connector's batched index quote (one Dhan call for every index).
"""

import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from connectors import cache, chart_connector

try:
    from dhanhq import dhanhq
except ImportError:  # pragma: no cover
    dhanhq = None

S3_KEY = "uploads/sector_indices.csv"
LOCAL_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sector_indices.csv")

EMA_PERIOD = 200
NEAR_EMA_PCT = 1.0
RSI_PERIOD = 14
RSI_MAX = 35.0
# Below this many bars the 200 EMA is still settling from its seed — shown
# as "approx." rather than hidden (Dhan only has ~1 year for its newest
# indices, e.g. Nifty 500 Momentum 50).
FULL_HISTORY_BARS = 400

RECENT_BARS = 30

HISTORY_DAYS = 3 * 365
HISTORY_CACHE_TTL_SECONDS = 6 * 60 * 60
LIST_CACHE_TTL_SECONDS = 60 * 60
# Dhan's data APIs are rate limited; a few at a time keeps a cold-cache
# load (~38 indices) well inside that while still finishing quickly.
HISTORY_FETCH_WORKERS = 4
HISTORY_FETCH_RETRIES = 3


def _as_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def _fetch_index_list():
    try:
        df = chart_connector.read_csv(S3_KEY)
        source = "s3"
    except Exception:
        df = pd.read_csv(LOCAL_CSV)
        source = "bundled"
    rows = []
    for r in df.to_dict(orient="records"):
        if not _as_bool(r.get("track", True)):
            continue
        rows.append({
            "securityId": int(r["security_id"]),
            "symbol": str(r["symbol"]).strip(),
            "name": str(r["display_name"]).strip(),
            "category": str(r["category"]).strip(),
            "investable": _as_bool(r.get("investable", True)),
            "sortOrder": int(r.get("sort_order") or 999),
        })
    rows.sort(key=lambda r: r["sortOrder"])
    return {"indices": rows, "source": source}


def get_index_list():
    return cache.get_or_fetch("sector_index_list", LIST_CACHE_TTL_SECONDS, _fetch_index_list)


def _fetch_history(security_id):
    to_date = datetime.datetime.now(chart_connector.IST).date()
    from_date = to_date - datetime.timedelta(days=HISTORY_DAYS)
    last_error = None
    for attempt in range(HISTORY_FETCH_RETRIES):
        try:
            resp = chart_connector._dhan().historical_daily_data(
                security_id=str(security_id), exchange_segment=dhanhq.INDEX, instrument_type="INDEX",
                from_date=from_date.isoformat(), to_date=to_date.isoformat(),
            )
            if resp.get("status") != "success":
                raise RuntimeError(resp.get("remarks") or "historical_daily_data failed")
            data = resp["data"]
            # Dhan stamps each daily bar at IST midnight — converting in
            # UTC would label every session one day early (Friday's bar
            # as Thursday), and then today's live bar would never line
            # up with it.
            dates = pd.to_datetime(data["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").strftime("%Y-%m-%d")
            return [
                {"time": d, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)}
                for d, o, h, l, c, v in zip(dates, data["open"], data["high"], data["low"], data["close"], data["volume"])
            ]
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"history for index {security_id} failed: {last_error}")


def _get_history(security_id):
    return cache.get_or_fetch(f"sector_index_history_{security_id}", HISTORY_CACHE_TTL_SECONDS, lambda: _fetch_history(security_id))


def ema(values, period):
    """Standard EMA seeded with the SMA of the first `period` values."""
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    for v in values[period:]:
        current = alpha * v + (1 - alpha) * current
    return current


def rsi(values, period=RSI_PERIOD):
    """Wilder's RSI — the same smoothing TradingView/Chartink use."""
    if len(values) <= period:
        return None
    changes = [b - a for a, b in zip(values, values[1:])]
    avg_gain = sum(max(c, 0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0) for c in changes[:period]) / period
    for c in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(c, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def evaluate(closes, investable=True):
    """Indicator values + rule outcome for one index's daily closes."""
    close = closes[-1]
    prev = closes[-2] if len(closes) > 1 else None
    ema_value = ema(closes, EMA_PERIOD)
    rsi_value = rsi(closes)
    dist_pct = (close - ema_value) / ema_value * 100 if ema_value else None
    price_ok = dist_pct is not None and dist_pct <= NEAR_EMA_PCT
    rsi_ok = rsi_value is not None and rsi_value < RSI_MAX
    month_ago = closes[-22] if len(closes) >= 22 else None
    return {
        "close": close,
        "changePct": (close - prev) / prev * 100 if prev else None,
        "change1mPct": (close - month_ago) / month_ago * 100 if month_ago else None,
        "ema200": ema_value,
        "distFromEmaPct": dist_pct,
        "rsi14": rsi_value,
        "priceCondition": price_ok,
        "rsiCondition": rsi_ok,
        "eligible": bool(investable and price_ok and rsi_ok),
        "bars": len(closes),
        "approx": len(closes) < FULL_HISTORY_BARS,
    }


def _merge_live(bars, live):
    """Put today's live bar on the end of the daily history. Outside a
    session (weekend, holiday, pre-open) Dhan's index quote replays the
    last session's OHLC stamped with today's date and volume 0 —
    chart_connector._merge_live_bar() compares volume too, so it treats
    that replay as a new day and appends a duplicate bar, which double-
    counts the last close in the EMA/RSI (confirmed live, NIFTY on
    Saturday 2026-09-26). Matching on OHLC alone catches it."""
    if not bars or not live:
        return bars
    last = bars[-1]
    if all(last[k] == live[k] for k in ("open", "high", "low", "close")):
        return bars
    if live["time"] == last["time"]:
        return bars[:-1] + [live]
    if live["time"] > last["time"]:
        return bars + [live]
    return bars


def _index_row(meta):
    bars = _get_history(meta["securityId"])
    try:
        bars = _merge_live(bars, chart_connector._get_live_index_bar(meta["securityId"]))
    except Exception:
        pass  # quote unavailable — the last daily close is fine
    bars = [b for b in bars if b["close"] > 0]
    closes = [b["close"] for b in bars]
    if len(closes) < 2:
        raise RuntimeError("not enough history")
    return {
        **meta,
        **evaluate(closes, meta["investable"]),
        "change": closes[-1] - closes[-2],
        # Day view's sparklines (30 sessions) and 5-day sector trend.
        "recent": [{"t": b["time"], "c": b["close"]} for b in bars[-RECENT_BARS:]],
        "asOf": bars[-1]["time"],
    }


def get_sector_overview():
    listing = get_index_list()
    metas = listing["indices"]
    with ThreadPoolExecutor(max_workers=HISTORY_FETCH_WORKERS) as pool:
        futures = [(meta, pool.submit(_index_row, meta)) for meta in metas]
    rows, failed = [], []
    for meta, future in futures:
        try:
            rows.append(future.result())
        except Exception as exc:
            failed.append({"symbol": meta["symbol"], "name": meta["name"], "error": str(exc)})
    return {
        "indices": rows,
        "failed": failed,
        "listSource": listing["source"],
        "rule": {"emaPeriod": EMA_PERIOD, "nearEmaPct": NEAR_EMA_PCT, "rsiPeriod": RSI_PERIOD, "rsiMax": RSI_MAX},
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
