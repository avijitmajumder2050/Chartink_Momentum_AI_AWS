"""DhanHQ connector — security-ID resolution and historical daily candles.

Dhan identifies instruments by a numeric security_id, not by trading symbol,
so every caller here that has a symbol ("INFY") must resolve it against
Dhan's published scrip master CSV first. That CSV is public (no auth), so
resolution is fetched with plain `pandas.read_csv`, not
`dhanhq.Security.fetch_security_list()` — the SDK method writes a CSV file
to disk as a side effect, which this connector doesn't want.

Credentials come from connectors/secrets.py (AWS SSM, same as every other
credential this user's systems already pull from Parameter Store), at
/dhan/client_id and /dhan/access_token — the same parameter names as the
user's other Dhan-based project (Dhan_MCP), so both point at the one Dhan
account.
"""

import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from dhanhq import DhanContext, dhanhq

from connectors import cache, secrets

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# Dhan's compact scrip master doesn't change intraday — securities list/
# delist and F&O contracts roll monthly, so a daily cache is more than
# enough (same reasoning as ai_verdict/marketsmith's 24h TTLs).
SECURITY_MASTER_CACHE_TTL_SECONDS = 24 * 60 * 60

# Historical daily candles only change once a day after market close;
# matches fundamentals_connector's PRICE_CACHE_TTL_SECONDS.
HISTORICAL_CACHE_TTL_SECONDS = 6 * 60 * 60

# The first 1-minute candle of a trading day, once formed, never changes
# again — but a request made before 09:16 IST legitimately has "no candle
# yet", and that None shouldn't get pinned as the cached answer for the
# rest of the day (connectors/cache.py caches failures/None just as
# eagerly as real results — see chart_connector.py's batch-quote fix for
# why that's usually exactly what's wanted, but not here). A moderate TTL
# means a pre-open request just gets naturally retried a few minutes
# later instead of staying wrong all day.
FIRST_MINUTE_CACHE_TTL_SECONDS = 20 * 60

_client = None


def _get_client():
    global _client
    if _client is None:
        client_id = secrets.get_parameter("/dhan/client_id")
        access_token = secrets.get_parameter("/dhan/access_token")
        _client = dhanhq(DhanContext(client_id, access_token))
    return _client


def _fetch_nse_equity_master():
    response = requests.get(SCRIP_MASTER_URL, timeout=30)
    response.raise_for_status()
    raw = pd.read_csv(io.BytesIO(response.content))

    # Filter values confirmed against a real download of this CSV — see
    # .agents/skills/dhanhq/references/instruments.md for the general
    # resolution approach; SEM_SEGMENT == "E" + SEM_INSTRUMENT_NAME ==
    # "EQUITY" is what actually isolates NSE cash-equity rows (spot-checked
    # against INFY/TCS), not a guess.
    nse_equity = raw[
        (raw["SEM_EXM_EXCH_ID"] == "NSE")
        & (raw["SEM_SEGMENT"] == "E")
        & (raw["SEM_INSTRUMENT_NAME"] == "EQUITY")
    ]

    df = (
        nse_equity[["SEM_TRADING_SYMBOL", "SEM_SMST_SECURITY_ID"]]
        .rename(columns={"SEM_TRADING_SYMBOL": "symbol", "SEM_SMST_SECURITY_ID": "security_id"})
        .drop_duplicates(subset="symbol")
    )
    # connectors/cache.py round-trips through JSON, so return plain records
    # here rather than a DataFrame.
    return df.to_dict(orient="records")


def get_nse_equity_master():
    """DataFrame with columns [symbol, security_id] for the NSE cash-equity
    universe. Cached to disk (connectors/cache.py) for a day."""
    records = cache.get_or_fetch("dhan_nse_equity_master", SECURITY_MASTER_CACHE_TTL_SECONDS, _fetch_nse_equity_master)
    return pd.DataFrame(records)


def resolve_security_ids(symbols):
    """Maps trading symbols to Dhan security_ids.

    Returns (resolved: dict[str, str], unresolved: list[str]) rather than
    raising on a miss — a stale/renamed symbol in ema_cross_watchlist.csv
    shouldn't take down the whole scan, same failure posture as this
    project's other connectors.
    """
    master = get_nse_equity_master()
    lookup = dict(zip(master["symbol"], master["security_id"].astype(str)))

    resolved = {}
    unresolved = []
    for symbol in symbols:
        security_id = lookup.get(symbol.upper())
        if security_id is None:
            unresolved.append(symbol)
        else:
            resolved[symbol] = security_id

    return resolved, unresolved


def _fetch_historical_daily(security_id, from_date, to_date):
    response = _get_client().historical_daily_data(
        security_id=security_id,
        exchange_segment=dhanhq.NSE,
        instrument_type="EQUITY",
        from_date=from_date,
        to_date=to_date,
    )

    if response.get("status") != "success":
        raise RuntimeError(f"Dhan historical_daily_data failed for {security_id}: {response.get('remarks')}")

    candles = response["data"]
    dates = pd.to_datetime(candles["timestamp"], unit="s").strftime("%Y-%m-%d")
    df = pd.DataFrame(
        {
            "date": dates,
            "open": candles["open"],
            "high": candles["high"],
            "low": candles["low"],
            "close": candles["close"],
            "volume": candles["volume"],
        }
    )
    # connectors/cache.py round-trips through JSON — "date" is a plain
    # YYYY-MM-DD string, not a Timestamp, precisely so this is serializable.
    return df.to_dict(orient="records")


def get_historical_daily(security_id, from_date, to_date):
    """List of daily candle dicts (date/open/high/low/close/volume) for one
    security_id, cached for HISTORICAL_CACHE_TTL_SECONDS.

    Callers should pass a stable, generously-wide date range (e.g. "last
    180 days") rather than moving the window every call — from_date/to_date
    are part of the cache key, so a `to_date` that changes every call (e.g.
    always "today") would never hit cache.
    """
    key = f"dhan_historical_{security_id}_{from_date}_{to_date}"
    rows = cache.get_or_fetch(key, HISTORICAL_CACHE_TTL_SECONDS, lambda: _fetch_historical_daily(security_id, from_date, to_date))
    return pd.DataFrame(rows)


def _fetch_intraday_minute(security_id, from_date, to_date, interval=1, max_retries=6, retry_delay=2):
    # Confirmed live (2026-09-18): this endpoint returns a DH-904 rate-limit
    # error under concurrent load, unlike historical_daily_data which
    # hasn't been observed to — retried with backoff rather than assumed
    # safe, same posture as chart_connector._get_quotes's batch retries.
    response = None
    for attempt in range(1, max_retries + 1):
        response = _get_client().intraday_minute_data(
            security_id=security_id,
            exchange_segment=dhanhq.NSE,
            instrument_type="EQUITY",
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )
        if response.get("status") == "success":
            break

        remarks = response.get("remarks")
        rate_limited = isinstance(remarks, dict) and remarks.get("error_code") == "DH-904"
        if rate_limited and attempt < max_retries:
            time.sleep(retry_delay * attempt)
            continue
        raise RuntimeError(f"Dhan intraday_minute_data failed for {security_id}: {remarks}")

    candles = response["data"]
    if not candles.get("timestamp"):
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    times = pd.to_datetime(candles["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata")
    return pd.DataFrame({
        "time": times,
        "open": candles["open"],
        "high": candles["high"],
        "low": candles["low"],
        "close": candles["close"],
        "volume": candles["volume"],
    })


def _row_to_candle(row):
    return {
        "time": row["time"].strftime("%H:%M"),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }


def _fetch_opening_move(security_id, date_str, lookback_days=6, interval=1):
    to_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    from_date = to_date - timedelta(days=lookback_days)
    # One intraday call spanning several days back through today's open
    # derives the previous session's close (its last candle at this
    # interval) AND today's first two candles — one Dhan call instead of
    # historical_daily_data + intraday_minute_data separately, which
    # matters a lot given this endpoint's confirmed-live rate limit and
    # that callers here (first_minute_movers.py) need this for many stocks
    # in one HTTP request. The window end (09:35) comfortably covers the
    # first two candles regardless of interval (1/5/15/25/60 minutes).
    df = _fetch_intraday_minute(security_id, f"{from_date.isoformat()} 09:15:00", f"{date_str} 09:35:00", interval=interval)
    if df.empty:
        return {"prev_close": None, "first_candle": None, "second_candle": None}

    day = df["time"].dt.strftime("%Y-%m-%d")
    prior = df[day < date_str]
    prev_close = float(prior.iloc[-1]["close"]) if not prior.empty else None

    today_rows = df[day == date_str]
    first_candle = _row_to_candle(today_rows.iloc[0]) if len(today_rows) >= 1 else None
    second_candle = _row_to_candle(today_rows.iloc[1]) if len(today_rows) >= 2 else None

    return {"prev_close": prev_close, "first_candle": first_candle, "second_candle": second_candle}


def get_opening_move(security_id, date_str, interval=1):
    """{prev_close, first_candle, second_candle} for `date_str` (YYYY-MM-DD)
    — first_candle/second_candle are {time, open, high, low, close, volume}
    for the first two candles of the day at `interval` minutes (1, 5, 15,
    25 or 60 — Dhan's supported intraday intervals; e.g. interval=5 -> the
    09:15-09:20 and 09:20-09:25 IST candles), or None if that candle hasn't
    formed yet that day (or there's no data at all, e.g. a trading
    holiday). prev_close is the previous session's last candle close at
    that same interval, or None if that couldn't be found either.

    A moderate (not full-day) cache TTL is used deliberately: once a candle
    has actually formed it never changes again, but a request made before
    it forms legitimately gets None, and that shouldn't get pinned as the
    cached answer for the rest of the day (connectors/cache.py caches
    failures/None just as eagerly as real results)."""
    key = f"dhan_opening_move_{security_id}_{date_str}_{interval}m"
    return cache.get_or_fetch(key, FIRST_MINUTE_CACHE_TTL_SECONDS, lambda: _fetch_opening_move(security_id, date_str, interval=interval))


# How close counts as "at" the circuit — 0.5%, same threshold used on
# the order-execution side (trading-bot-algo's dhan_super_client.py)
# for consistency between the two independent checks.
CIRCUIT_PROXIMITY_FRACTION = 0.005


def get_circuit_limits(security_id, segment="NSE_EQ", max_attempts=3, retry_delay=1):
    """(ltp, lower_circuit_limit, upper_circuit_limit) from a live Dhan
    quote — deliberately not cached (unlike everything else in this
    file): a circuit check is only meaningful against the current
    price, not a stale one. Any of the three can be None if every
    attempt fails or that field is missing.

    A few retries, not a single bare attempt: Dhan's quote endpoint is
    flaky enough in practice (confirmed live, 2026-09-22 night) that a
    single-shot fetch would too often "fail closed" in near_circuit()
    below and block a real, otherwise-valid setup on a transient blip
    rather than an actual circuit condition.

    Used to reject a stock at qualify time, before it ever becomes a
    "New watch" alert — not just at order-placement time. Confirmed
    live (TBZ, 2026-09-22): a circuit-frozen stock can still produce a
    qualifying-looking candle shape, so this checks Dhan's own
    authoritative circuit data directly rather than only inferring it
    from candle shape."""
    client = _get_client()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.quote_data(securities={segment: [int(security_id)]})
            data = resp.get("data", {}) if isinstance(resp, dict) else {}
            inner = data.get("data", {}) if isinstance(data, dict) else {}
            seg_data = inner.get(segment, {}) if isinstance(inner, dict) else {}
            quote = seg_data.get(str(security_id)) if isinstance(seg_data, dict) else None
            if not quote or not isinstance(quote, dict):
                raise ValueError(f"Empty or invalid quote: {quote}")
            ltp = quote.get("last_price")
            if ltp is None:
                raise ValueError("last_price missing in quote")
            lower = quote.get("lower_circuit_limit")
            upper = quote.get("upper_circuit_limit")
            return (
                float(ltp),
                float(lower) if lower is not None else None,
                float(upper) if upper is not None else None,
            )
        except Exception:
            if attempt < max_attempts:
                time.sleep(retry_delay)
    return None, None, None


def near_circuit(security_id):
    """True if security_id's live price is within CIRCUIT_PROXIMITY_
    FRACTION of either circuit limit (or the quote genuinely couldn't
    be fetched — fail closed, since a qualify-time reject is cheap and
    a false negative here is a real risk, not just noise)."""
    ltp, lower, upper = get_circuit_limits(security_id)
    if ltp is None or lower is None or upper is None:
        return True
    if upper > 0 and ltp >= upper * (1 - CIRCUIT_PROXIMITY_FRACTION):
        return True
    if lower > 0 and ltp <= lower * (1 + CIRCUIT_PROXIMITY_FRACTION):
        return True
    return False
