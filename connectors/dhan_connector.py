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
