"""Real daily OHLCV chart data — ported from the user's own reference
backend (TradeChartsMazaview/backend/tradingview_helper.py). Same S3
bucket/layout: uploads/mapping.csv maps NSE symbol -> Instrument ID,
eod_data/{instrument_id}.csv holds daily OHLCV bars.

Self-contained (own S3 client, own Dhan client) rather than depending on
connectors/dhan_connector.py — that module has since moved to a different
design (Dhan's own scrip master + historical_daily_data API, full NSE
universe, no live-quote method), which this chart still needs, but the two
aren't reconciled yet. Revisit merging them once that settles.

Two layers, same idea as dhan_ema_breakout.py's _update_today_candle:
- EOD bars from eod_data/{instrument_id}.csv, cached for hours — the CSV
  itself only updates once a day, so there's no need to re-fetch it often.
- Today's live quote from Dhan, cached for a much shorter window and
  merged on top of the EOD bars on every call. Without this, the chart's
  last bar would be stuck at yesterday's close all through market hours,
  which is the "CSV has one-day-old data" complaint this connector exists
  to fix. Quoted in one batched call for every instrument in the
  watchlist (chunked at 1,000/request per Dhan's limit, retried up to 7
  times on failure) rather than one Dhan API call per symbol per chart
  view — the whole watchlist shares that one cached batch.

Best-effort throughout: a missing symbol, an S3 miss, or a failed live
quote all degrade gracefully — a failed live quote just means the chart
falls back to EOD-only for that view rather than breaking the page.
"""

import datetime
import io
import json
import threading
import time

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from dhanhq import DhanContext, dhanhq
except ImportError:
    DhanContext = None
    dhanhq = None

import pandas as pd
import pytz
import requests

from connectors import cache, dhan_connector, secrets

AWS_REGION = "ap-south-1"
# Same bucket-probe order as the reference aws_s3.py.
BUCKET_CANDIDATES = ["dhan-trading-data", "new-dhan-trading-data"]
MAPPING_KEY = "uploads/mapping.csv"
EOD_PREFIX = "eod_data"

# Indices (NIFTY 50, BANKNIFTY, sector indices, SENSEX, ...) — same file
# upload_security_master.py uploads monthly, read from there first so this
# doesn't depend on Dhan's CDN being reachable at request time; falls back
# to fetching it live if that S3 object doesn't exist yet.
SECURITY_MASTER_S3_KEY = "uploads/dhan_security_master.csv"
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
# Common names people actually type -> Dhan's own SEM_TRADING_SYMBOL, both
# sides space-stripped (see _resolve_index_symbol — everything is matched
# space-free, since app.py's _normalize_symbol already strips the space out
# of whatever the user typed before this connector ever sees it, and Dhan's
# own index names are inconsistent about using one: "NIFTYIT" has none,
# but "NIFTY AUTO"/"NIFTY PSU BANK" do).
INDEX_ALIASES = {
    "NIFTY50": "NIFTY",
}

# Fallback path (symbol missing from mapping.csv, or mapped but with no
# eod_data/{id}.csv): calendar days to ask Dhan for, generous enough to
# comfortably cover FALLBACK_CANDLE_COUNT trading days after weekends/
# holidays are excluded.
FALLBACK_HISTORY_DAYS = 300
FALLBACK_CANDLE_COUNT = 200

MAPPING_CACHE_TTL_SECONDS = 60 * 60
OHLCV_CACHE_TTL_SECONDS = 6 * 60 * 60
# Short — this is what makes the chart feel live rather than re-fetching
# on every keystroke; long enough that switching symbols back and forth
# doesn't hammer Dhan's API.
LIVE_QUOTE_CACHE_TTL_SECONDS = 60

IST = pytz.timezone("Asia/Kolkata")

_bucket = None
_dhan_client = None


def _s3():
    if boto3 is None:
        raise RuntimeError("boto3 is not installed")
    return boto3.client("s3", region_name=AWS_REGION)


def _get_bucket(client):
    global _bucket
    if _bucket:
        return _bucket
    for candidate in BUCKET_CANDIDATES:
        try:
            client.head_bucket(Bucket=candidate)
            _bucket = candidate
            return _bucket
        except Exception:
            continue
    raise RuntimeError(f"none of {BUCKET_CANDIDATES} are accessible")


DHAN_HTTP_TIMEOUT_SECONDS = 8  # dhanhq's own default is 60s per request; with
# up to 7 retries in _get_quotes, an unresponsive Dhan API at the default
# timeout can block a caller for 7+ minutes. A stalled quote request should
# fail fast and retry, not hang the whole watchlist/dashboard behind it.


def _dhan():
    global _dhan_client
    if dhanhq is None:
        raise RuntimeError("dhanhq is not installed")
    if _dhan_client is None:
        client_id = secrets.get_parameter("/dhan/client_id")
        access_token = secrets.get_parameter("/dhan/access_token")
        _dhan_client = dhanhq(DhanContext(client_id, access_token))
        _dhan_client.dhan_http.timeout = DHAN_HTTP_TIMEOUT_SECONDS
    return _dhan_client


def _fetch_mapping():
    client = _s3()
    bucket = _get_bucket(client)
    obj = client.get_object(Bucket=bucket, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name", "Instrument ID"])
    return {
        str(row["Stock Name"]).strip().upper(): int(row["Instrument ID"])
        for _, row in df.iterrows()
    }


def _get_mapping():
    return cache.get_or_fetch("chart_symbol_mapping", MAPPING_CACHE_TTL_SECONDS, _fetch_mapping)


def _fetch_eod_bars(instrument_id):
    client = _s3()
    bucket = _get_bucket(client)
    obj = client.get_object(Bucket=bucket, Key=f"{EOD_PREFIX}/{instrument_id}.csv")
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df.columns = [c.strip().lower() for c in df.columns]

    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"eod_data/{instrument_id}.csv missing columns: {missing}")

    df = df[required].dropna()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    return [
        {
            # lightweight-charts wants YYYY-MM-DD for daily bars, not a
            # unix timestamp (that's for intraday time-based series)
            "time": row["date"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in df.iterrows()
    ]


def _get_eod_bars(instrument_id):
    key = f"chart_ohlcv_{instrument_id}"
    return cache.get_or_fetch(key, OHLCV_CACHE_TTL_SECONDS, lambda: _fetch_eod_bars(instrument_id))


def _get_quotes(security_ids, segment, retry_delay=1, max_retries=7):
    """Batched live quotes for `security_ids` in `segment` (e.g. "NSE_EQ"),
    chunked at 1,000 instruments/request per Dhan's limit and retried on
    failure — same batching/retry shape as dhan_ema_breakout.py used with
    the old dhan_connector.get_quotes, kept here directly since that
    function no longer exists on the (differently-scoped) current
    dhan_connector.py.

    Returns {security_id: quote_dict} for whatever it could fetch, or None
    if nothing came back at all.
    """
    dhan = _dhan()
    all_quotes = {}

    for i in range(0, len(security_ids), 1000):
        batch_ids = security_ids[i:i + 1000]

        for attempt in range(1, max_retries + 1):
            try:
                quote_data = dhan.quote_data(securities={segment: batch_ids})
                if isinstance(quote_data, str):
                    quote_data = json.loads(quote_data)

                segment_quotes = quote_data.get("data", {}).get("data", {}).get(segment)
                if not isinstance(segment_quotes, dict):
                    raise ValueError(f"Invalid quote payload: {quote_data}")

                all_quotes.update(segment_quotes)
                break
            except Exception:
                if attempt < max_retries:
                    time.sleep(retry_delay)
        time.sleep(1)

    return all_quotes or None


def _fetch_live_quotes_batch():
    """One batched Dhan call for every instrument in the watchlist — same
    shape as dhan_ema_breakout.py's live_data fetch. Quoting instruments
    one-by-one (a separate API call per chart view) is exactly the pattern
    that runs into Dhan's rate limits; a single batched call serves every
    symbol in the watchlist from one round trip, cached together."""
    mapping = _get_mapping()
    instrument_ids = list(mapping.values())
    quotes = _get_quotes(instrument_ids, "NSE_EQ", max_retries=3)
    if not quotes:
        raise RuntimeError("no live quotes returned")
    return quotes


_live_quotes_memory_cache = None  # (cached_at, data) — see _get_live_quotes_batch
_live_quotes_lock = threading.Lock()


def _get_live_quotes_batch():
    # cache.get_or_fetch's file cache still gets hit on every call within
    # the TTL window — it's a full JSON read + parse of ~350+ symbols'
    # worth of quotes every time, not free. That was measured as a real
    # bottleneck: every get_ohlcv() call for a mapped symbol goes through
    # here, and several concurrent calls (e.g. the dashboard's watchlist,
    # 5 stocks fetched in parallel) were each independently re-parsing
    # that same file, serialized by the GIL since JSON parsing is
    # CPU-bound. This in-process layer on top avoids that — with a lock,
    # not just a bare check, since without one every one of those
    # concurrent threads sees an empty cache at the same instant and each
    # redundantly re-fetches anyway, which is exactly what a plain
    # (unlocked) check-then-populate does under real concurrent load.
    global _live_quotes_memory_cache
    if _live_quotes_memory_cache is not None:
        cached_at, data = _live_quotes_memory_cache
        if time.time() - cached_at < LIVE_QUOTE_CACHE_TTL_SECONDS:
            return data

    with _live_quotes_lock:
        # Re-check — another thread may have refreshed it while this one
        # was waiting for the lock, in which case there's nothing to do.
        if _live_quotes_memory_cache is not None:
            cached_at, data = _live_quotes_memory_cache
            if time.time() - cached_at < LIVE_QUOTE_CACHE_TTL_SECONDS:
                return data

        try:
            data = cache.get_or_fetch("chart_live_quotes_batch", LIVE_QUOTE_CACHE_TTL_SECONDS, _fetch_live_quotes_batch)
        except Exception:
            # Remember the failure too (e.g. market closed, Dhan down) —
            # without this, every one of the ~356 concurrent get_ohlcv()
            # calls that reach here while quotes are unavailable would
            # each redo the full ~27s Dhan retry storm itself, serialized
            # behind this same lock (up to 356 x 27s ~ minutes for the
            # whole watchlist scan instead of one ~27s failure shared by
            # all of them).
            data = None
        _live_quotes_memory_cache = (time.time(), data)
        return data


def _live_bar_from_quote(live):
    if not live or "ohlc" not in live:
        raise RuntimeError("live quote missing OHLC")

    ohlc = live["ohlc"]
    today = datetime.datetime.now(IST).strftime("%Y-%m-%d")
    return {
        "time": today,
        "open": float(ohlc.get("open", 0)),
        "high": float(ohlc.get("high", 0)),
        "low": float(ohlc.get("low", 0)),
        "close": float(live.get("last_price", ohlc.get("close", 0))),
        "volume": float(live.get("volume", 0)),
    }


def _get_live_bar(instrument_id):
    quotes = _get_live_quotes_batch()
    return _live_bar_from_quote(quotes.get(str(instrument_id)) if quotes else None)


def get_live_change_pct_batch(security_ids):
    """{security_id: pct_change} from the SAME batched/cached live-quote
    call every other live price on this site already uses — a cheap way
    to rank a large universe (e.g. the whole watchlist) by how far each
    stock has already moved today, before doing something expensive
    per-symbol for only the stocks that matter (see first_minute_movers.py,
    which uses this to shortlist candidates before spending Dhan's tightly
    rate-limited intraday-candle calls on just those).

    Computed as last_price vs the quote's own ohlc.close. During market
    hours that reflects the previous session's close (the standard "gap %"
    definition); Dhan appears to roll ohlc.close over to today's own close
    once the market has shut, so this is only meaningful as a same-day
    shortlist signal, not a stable previous-close source in general —
    callers that need an authoritative previous close (or already-final
    Change %) should compute it themselves for their shortlisted subset,
    not trust this batch for the final number.
    """
    quotes = _get_live_quotes_batch()
    if not quotes:
        return {}

    result = {}
    for security_id in security_ids:
        quote = quotes.get(str(security_id))
        if not quote or "ohlc" not in quote:
            continue
        prev_close = quote["ohlc"].get("close")
        last_price = quote.get("last_price")
        if not prev_close or last_price is None:
            continue
        result[str(security_id)] = (last_price - prev_close) / prev_close * 100
    return result


def get_live_circuit_status(instrument_id):
    """Precise (not guessed) upper/lower circuit status for one
    instrument, straight from Dhan's own quote_data fields
    (upper_circuit_limit / lower_circuit_limit) — reads from the SAME
    already-cached whole-watchlist batch _get_live_bar uses, so this is
    free (no extra API call) whenever that batch is warm.

    Returns {"at_circuit": "upper" | "lower" | None, "upper_limit":
    float, "lower_limit": float} or None if live data isn't available
    (outside market hours, quote fetch failed, symbol not in the
    watchlist mapping, etc.) — callers should treat None as "unknown",
    not "not at circuit"."""
    quotes = _get_live_quotes_batch()
    live = quotes.get(str(instrument_id)) if quotes else None
    if not live:
        return None

    try:
        upper_limit = float(live["upper_circuit_limit"])
        lower_limit = float(live["lower_circuit_limit"])
        last_price = float(live.get("last_price", 0))
    except (KeyError, TypeError, ValueError):
        return None

    if upper_limit <= 0 or lower_limit <= 0:
        return None  # Dhan sometimes has no band for a symbol (e.g. no circuit)

    # A tiny tolerance for float/rounding noise — the exchange freezes the
    # price at exactly the limit, but paise-level float comparison can
    # miss by a fraction otherwise.
    at_circuit = None
    if last_price >= upper_limit - 0.01:
        at_circuit = "upper"
    elif last_price <= lower_limit + 0.01:
        at_circuit = "lower"

    return {"at_circuit": at_circuit, "upper_limit": upper_limit, "lower_limit": lower_limit}


def get_live_ohlc(security_ids):
    """Batched live high/low/close straight from Dhan's quote_data API, for
    a caller-supplied list of security_ids — not the cached whole-watchlist
    batch the chart views use, since this exists for scanners (e.g.
    chartink_stoch_backtest.py) that want a fallback for a specific handful
    of just-matched symbols, not the full instrument universe.

    Best-effort like everything else in this file: never raises, returns
    {security_id: {"high", "low", "close"}} for whatever it could fetch —
    an empty dict on total failure just means the caller keeps whatever
    (possibly missing) values it already had."""
    quotes = _get_quotes([str(s) for s in security_ids], "NSE_EQ", max_retries=3)
    if not quotes:
        return {}
    result = {}
    for security_id, quote in quotes.items():
        try:
            bar = _live_bar_from_quote(quote)
        except Exception:
            continue
        result[security_id] = {"high": bar["high"], "low": bar["low"], "close": bar["close"]}
    return result


def _merge_live_bar(bars, live_bar):
    if not bars:
        return bars + [live_bar]

    last = bars[-1]
    # Outside trading hours (weekend/holiday/pre-open) Dhan's quote endpoint
    # keeps returning the last session's own OHLC/volume, just stamped with
    # today's date — appending that verbatim would duplicate the last real
    # session as a second candle, double-weighting it in every EMA and
    # masking genuine crosses (e.g. Friday's candle repeated as "Sunday").
    # A live bar that's byte-identical to the last EOD bar is that replay,
    # not a new session, so it's dropped rather than appended/merged.
    if (
        last["open"] == live_bar["open"]
        and last["high"] == live_bar["high"]
        and last["low"] == live_bar["low"]
        and last["close"] == live_bar["close"]
        and last["volume"] == live_bar["volume"]
    ):
        return bars

    if last["time"] == live_bar["time"]:
        return bars[:-1] + [live_bar]
    return bars + [live_bar]


def _fetch_index_master():
    try:
        client = _s3()
        bucket = _get_bucket(client)
        obj = client.get_object(Bucket=bucket, Key=SECURITY_MASTER_S3_KEY)
        raw = obj["Body"].read()
    except Exception:
        # S3 copy missing (e.g. upload_security_master.py hasn't run yet) —
        # fall back to Dhan's own CDN rather than fail outright.
        response = requests.get(SCRIP_MASTER_URL, timeout=30)
        response.raise_for_status()
        raw = response.content

    df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    idx = df[(df["SEM_SEGMENT"] == "I") & (df["SEM_INSTRUMENT_NAME"] == "INDEX")]
    # Keyed space-free — Dhan's own index names aren't consistent about
    # spacing ("NIFTY AUTO" has one, "NIFTYIT" doesn't), and app.py's
    # _normalize_symbol already strips spaces out of whatever the user
    # typed before this connector ever sees it, so a space-free key is
    # what every lookup will actually be in practice.
    return {
        str(row["SEM_TRADING_SYMBOL"]).strip().upper().replace(" ", ""): int(row["SEM_SMST_SECURITY_ID"])
        for _, row in idx.iterrows()
    }


def _get_index_master():
    return cache.get_or_fetch("chart_index_master", MAPPING_CACHE_TTL_SECONDS, _fetch_index_master)


def _resolve_index_symbol(symbol):
    symbol = symbol.strip().upper().replace(" ", "")
    symbol = INDEX_ALIASES.get(symbol, symbol)
    return _get_index_master().get(symbol)


def _fetch_index_bars(security_id):
    to_date = datetime.datetime.now(IST).date()
    from_date = to_date - datetime.timedelta(days=FALLBACK_HISTORY_DAYS)

    response = _dhan().historical_daily_data(
        security_id=str(security_id),
        exchange_segment=dhanhq.INDEX,
        instrument_type="INDEX",
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )
    if response.get("status") != "success":
        raise RuntimeError(f"Dhan historical_daily_data failed for index {security_id}: {response.get('remarks')}")

    candles = response["data"]
    dates = pd.to_datetime(candles["timestamp"], unit="s").strftime("%Y-%m-%d")
    bars = [
        {
            "time": d,
            "open": float(o),
            "high": float(h),
            "low": float(low),
            "close": float(c),
            "volume": float(v),
        }
        for d, o, h, low, c, v in zip(
            dates, candles["open"], candles["high"], candles["low"], candles["close"], candles["volume"]
        )
    ]
    if not bars:
        raise RuntimeError(f"no historical data from Dhan for index {security_id}")
    return bars[-FALLBACK_CANDLE_COUNT:]


def _get_index_bars(security_id):
    key = f"chart_index_bars_{security_id}"
    return cache.get_or_fetch(key, OHLCV_CACHE_TTL_SECONDS, lambda: _fetch_index_bars(security_id))


def _fetch_live_index_quotes_batch():
    """One batched Dhan call for every index Dhan publishes, not one call
    per index requested — the dashboard alone resolves ~6 market indices
    + ~6 sector indices, each of which used to be its own separate
    quote_data() round trip (_get_live_index_bar's old per-security_id
    cache key) purely because whichever index happened to be resolved
    first was the only one in that call's batch. Same fix as stocks
    already got in _fetch_live_quotes_batch — quote every index the app
    might ask about in one request, shared by every caller."""
    security_ids = list(_get_index_master().values())
    quotes = _get_quotes(security_ids, "IDX_I", max_retries=3)
    if not quotes:
        raise RuntimeError("no live index quotes returned")
    return quotes


_live_index_quotes_memory_cache = None  # (cached_at, data) — see _get_live_index_quotes_batch
_live_index_quotes_lock = threading.Lock()


def _get_live_index_quotes_batch():
    # Same double-checked-locking shape as _get_live_quotes_batch() for
    # stocks, including caching a failure too (not just a success) — see
    # that function's comments for why both matter under concurrent load.
    global _live_index_quotes_memory_cache
    if _live_index_quotes_memory_cache is not None:
        cached_at, data = _live_index_quotes_memory_cache
        if time.time() - cached_at < LIVE_QUOTE_CACHE_TTL_SECONDS:
            return data

    with _live_index_quotes_lock:
        if _live_index_quotes_memory_cache is not None:
            cached_at, data = _live_index_quotes_memory_cache
            if time.time() - cached_at < LIVE_QUOTE_CACHE_TTL_SECONDS:
                return data

        try:
            data = cache.get_or_fetch("chart_live_index_quotes_batch", LIVE_QUOTE_CACHE_TTL_SECONDS, _fetch_live_index_quotes_batch)
        except Exception:
            data = None
        _live_index_quotes_memory_cache = (time.time(), data)
        return data


def _get_live_index_bar(security_id):
    quotes = _get_live_index_quotes_batch()
    if not quotes:
        raise RuntimeError("no live index quote")
    return _live_bar_from_quote(quotes.get(str(security_id)))


def get_ohlcv(symbol):
    symbol = symbol.upper()

    # 1. Stock universe (S3 watchlist)
    mapping = _get_mapping()
    instrument_id = mapping.get(symbol)

    if instrument_id is not None:
        try:
            bars = _get_eod_bars(instrument_id)
        except Exception:
            bars = None

        if bars:
            try:
                live_bar = _get_live_bar(instrument_id)
                bars = _merge_live_bar(bars, live_bar)
            except Exception:
                pass  # EOD-only is still a valid chart — the live quote is a bonus
            return bars
        # in mapping.csv but no eod_data/{id}.csv (or it's empty) — fall
        # through rather than give up

    # 2. Indices (NIFTY 50, BANKNIFTY, sector indices, SENSEX, ...)
    index_security_id = _resolve_index_symbol(symbol)
    if index_security_id is not None:
        bars = _get_index_bars(index_security_id)
        try:
            live_bar = _get_live_index_bar(index_security_id)
            bars = _merge_live_bar(bars, live_bar)
        except Exception:
            pass
        return bars

    # 3. NSE equity fallback via Dhan's security master (not in the S3 watchlist)
    return _fetch_fallback_ohlcv(symbol)


def _fetch_fallback_ohlcv(symbol):
    """Used when a symbol isn't in mapping.csv, or is but has no usable
    OHLC data there. Resolves the symbol against Dhan's own NSE security
    master (dhan_connector.resolve_security_ids — that master is fetched
    once and cached 24h by dhan_connector itself, so this doesn't
    re-download it per lookup) and pulls ~200 daily candles plus a live
    bar directly from Dhan, so a symbol missing from the S3 watchlist
    still gets a real chart instead of just failing."""
    resolved, _unresolved = dhan_connector.resolve_security_ids([symbol])
    security_id = resolved.get(symbol)
    if security_id is None:
        raise LookupError(f"symbol {symbol!r} not found in mapping.csv or Dhan's security master")

    to_date = datetime.datetime.now(IST).date()
    from_date = to_date - datetime.timedelta(days=FALLBACK_HISTORY_DAYS)
    df = dhan_connector.get_historical_daily(security_id, from_date.isoformat(), to_date.isoformat())
    if df is None or df.empty:
        raise RuntimeError(f"no historical data from Dhan for {symbol!r}")

    bars = [
        {
            "time": row["date"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in df.tail(FALLBACK_CANDLE_COUNT).iterrows()
    ]

    try:
        # dhan_connector.resolve_security_ids() hands back security_id as a
        # string, but Dhan's quote_data() silently fails (status: "failure")
        # unless it's an int — same fields either way for the historical
        # call above, so only this call needs the cast.
        quotes = _get_quotes([int(security_id)], "NSE_EQ", max_retries=7)
        if quotes:
            live_bar = _live_bar_from_quote(quotes.get(str(security_id)))
            bars = _merge_live_bar(bars, live_bar)
    except Exception:
        pass  # EOD-only fallback is still a valid chart

    return bars


def get_top_symbols(limit=12):
    """Symbol list sorted by RS Rating, for a real (not mock) watchlist
    sidebar — same mapping.csv the chart itself is keyed against."""
    client = _s3()
    bucket = _get_bucket(client)
    obj = client.get_object(Bucket=bucket, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name"])
    if "RS Rating" in df.columns:
        df["RS Rating"] = pd.to_numeric(df["RS Rating"], errors="coerce").fillna(0)
        df = df.sort_values("RS Rating", ascending=False)
    return [
        {"symbol": str(row["Stock Name"]).strip().upper(), "rsRating": row.get("RS Rating")}
        for _, row in df.head(limit).iterrows()
    ]


def get_top_symbols_cached(limit=12):
    return cache.get_or_fetch(f"chart_top_symbols_{limit}", MAPPING_CACHE_TTL_SECONDS, lambda: get_top_symbols(limit))


def _num_or_none(value):
    n = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(n) else float(n)


def get_watchlist_stocks():
    """Full mapping.csv watchlist (all rows, not just the top N) with the
    fields the multi-chart wall filters on: RS Rating, EPS Strength, Price
    Strength, Setup_Case, Market Cap. Used for the "no symbol selected ->
    show every watchlist stock" grid, and as the source list the EPS/Price
    Strength range filters and Setup Case filter run against client-side."""
    client = _s3()
    bucket = _get_bucket(client)
    obj = client.get_object(Bucket=bucket, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name"])

    return [
        {
            "symbol": str(row["Stock Name"]).strip().upper(),
            "rsRating": _num_or_none(row.get("RS Rating")),
            "epsStrength": _num_or_none(row.get("EPS Strength")),
            "priceStrength": _num_or_none(row.get("Price Strength")),
            "marketCap": _num_or_none(row.get("Market Cap")),
            "setupCase": str(row["Setup_Case"]).strip() if pd.notna(row.get("Setup_Case")) else None,
        }
        for _, row in df.iterrows()
    ]


def get_watchlist_stocks_cached():
    return cache.get_or_fetch("chart_watchlist_stocks", MAPPING_CACHE_TTL_SECONDS, get_watchlist_stocks)


def get_symbol_mapping():
    """Public wrapper around the cached symbol -> instrument_id mapping, for
    callers outside this connector (e.g. dhan_ema_breakout.py) that need the
    instrument_id alongside get_ohlcv()'s bars."""
    return _get_mapping()


def read_csv(key):
    """Read an arbitrary CSV from the same bucket this connector already
    resolves (BUCKET_CANDIDATES), for callers that need occasional ad-hoc S3
    access beyond mapping.csv/eod_data (e.g. dhan_ema_breakout.py's weekly
    output file)."""
    client = _s3()
    bucket = _get_bucket(client)
    obj = client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def write_csv(key, df):
    """Write a DataFrame as CSV to the same bucket."""
    client = _s3()
    bucket = _get_bucket(client)
    body = df.to_csv(index=False).encode("utf-8")
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/csv")
