"""First-opening-candle gainers/losers scanner — Dhan-based, alongside this
file's siblings (dhan_ema_breakout.py, chartink_stoch_backtest.py).

Ranks stocks by % change of their first candle of the trading day (09:15-
09:20 IST close, at INTERVAL_MINUTES) vs the previous session's close — an
early read on which names are moving right at the open, not a full-day
gainer/loser list.

Two stages, not one straight scan of the whole watchlist:

1. Shortlist cheaply. Dhan's intraday-candle endpoint has a real, tight,
   confirmed-live rate limit (DH-904 "Too many requests") — scanning all
   ~350 watchlist stocks individually (each needing its own API call, no
   batch mode exists for it) would take minutes and blow well past any
   reasonable HTTP request timeout. chart_connector.get_live_snapshot_
   batch() reuses the SAME batched/cached live-quote call every other live
   price on this site already makes — one cheap request covers the whole
   watchlist — to rank every stock by its live % move so far today, with
   only the most extreme ~20 on each side becoming candidates. This step
   only ranks; it deliberately does NOT filter by volume (day-cumulative
   volume from a live quote doesn't tell you anything about the opening
   candle itself), so the pool is kept larger than the final top_n to
   leave enough headroom for step 2's real filter to drop some.

2. Verify precisely, and filter by the RIGHT volume. Only for that short
   candidate list, dhan_connector.get_opening_move() is called (one
   throttled, retried Dhan request per candidate) to get the REAL
   first-candle OHLCV and previous session close — the actual numbers
   reported come from here, not the cheap shortlist step. Candidates whose
   first candle traded under MIN_CANDLE_VOLUME are dropped here: a handful
   of shares changing hands in a thin name can move its price several
   percent on noise alone, and that's only visible once the real candle's
   own volume is known, not from a day-cumulative proxy.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import pytz

from connectors import chart_connector, dhan_connector

IST = pytz.timezone("Asia/Kolkata")

# Candle size for "first candle of the day" — 5 -> the 09:15-09:20 IST
# candle. One of Dhan's supported intraday intervals: 1, 5, 15, 25, 60.
INTERVAL_MINUTES = 5

# Liquidity floor on the first candle's OWN volume (not the day's
# cumulative volume so far — that says nothing about how actively the
# opening candle itself traded). A handful of shares changing hands in a
# thin name can move its price several percent on noise alone; this is
# what actually screens that out.
MIN_CANDLE_VOLUME = 20_000

# How many candidates to verify precisely on each side (gainers/losers) —
# comfortably more than top_n so a shortlisting miss, or a candidate later
# dropped for thin first-candle volume, still leaves enough to fill a
# top 10. In practice a large fraction of shortlisted candidates get
# dropped for MIN_CANDLE_VOLUME (verified live: only 15 of 40 candidates
# survived at CANDIDATE_POOL=20, leaving one side short of a full top 10),
# so this needs real headroom, not just a small margin over top_n.
CANDIDATE_POOL = 30

# Dhan's intraday endpoint's rate limit (see module docstring) — modest on
# purpose even though only ~30 calls are made now, not assumed safe.
MAX_WORKERS = 3
SUBMIT_STAGGER_SECONDS = 0.5

logger = logging.getLogger(__name__)


def _pct_change(prev_close, current):
    if not prev_close:
        return None
    return round((current - prev_close) / prev_close * 100, 2)


def _verify_one(symbol, security_id, date_str, day_volume):
    try:
        move = dhan_connector.get_opening_move(security_id, date_str, interval=INTERVAL_MINUTES)
    except Exception as exc:
        logger.warning("%s skipped - %s", symbol, exc)
        return None

    prev_close, candle = move["prev_close"], move["first_candle"]
    if prev_close is None or candle is None:
        return None

    if candle["volume"] < MIN_CANDLE_VOLUME:
        return None

    change_pct = _pct_change(prev_close, candle["close"])
    if change_pct is None:
        return None

    return {
        "Stock Name": symbol,
        "Security ID": security_id,
        "Prev Close": round(prev_close, 2),
        "Open": round(candle["open"], 2),
        "High": round(candle["high"], 2),
        "Low": round(candle["low"], 2),
        "Close": round(candle["close"], 2),
        "Volume": candle["volume"],
        "Day Volume": day_volume,
        "Change %": change_pct,
        "First Candle Time": candle["time"],
    }


def get_first_minute_gainers_losers(top_n=10):
    """Returns (gainers_df, losers_df), each up to top_n rows, sorted by
    Change % (descending for gainers, ascending for losers). Both empty if
    the market hasn't opened yet or nothing could be verified. Gainers and
    losers never overlap even when the verified set is smaller than
    2 x top_n."""
    logger.info("First-%smin-candle gainers/losers scan started", INTERVAL_MINUTES)

    today = datetime.now(IST)
    date_str = today.strftime("%Y-%m-%d")

    stocks = chart_connector.get_watchlist_stocks_cached()
    symbols = [s["symbol"] for s in stocks]
    resolved, unresolved = dhan_connector.resolve_security_ids(symbols)
    if unresolved:
        logger.info("Skipping %s unresolved symbols", len(unresolved))

    snapshot = chart_connector.get_live_snapshot_batch(resolved.values())
    ranked = sorted(
        (
            (symbol, sid, snapshot[sid]["changePct"], snapshot[sid]["volume"])
            for symbol, sid in resolved.items()
            if sid in snapshot
        ),
        key=lambda row: row[2],
    )
    logger.info("Live quotes available for %s of %s resolved stocks", len(ranked), len(resolved))

    loser_candidates = ranked[:CANDIDATE_POOL]
    gainer_candidates = ranked[-CANDIDATE_POOL:]
    candidates = {}
    for symbol, sid, _, day_volume in loser_candidates + gainer_candidates:
        candidates[symbol] = (sid, day_volume)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = []
        for symbol, (security_id, volume) in candidates.items():
            futures.append(pool.submit(_verify_one, symbol, security_id, date_str, volume))
            time.sleep(SUBMIT_STAGGER_SECONDS)
        for future in futures:
            row = future.result()
            if row is not None:
                results.append(row)

    logger.info("First candles verified for %s of %s candidates", len(results), len(candidates))

    df = pd.DataFrame(results)
    if df.empty:
        return df, df

    sorted_df = df.sort_values("Change %", ascending=False).reset_index(drop=True)
    gainers = sorted_df.head(top_n).copy()
    gainers["Type"] = "Gainer"

    remaining = max(0, len(sorted_df) - len(gainers))
    losers = sorted_df.tail(min(top_n, remaining)).sort_values("Change %").reset_index(drop=True).copy()
    losers["Type"] = "Loser"

    return gainers, losers


if __name__ == "__main__":
    gainers_df, losers_df = get_first_minute_gainers_losers()
    print("Top gainers:\n", gainers_df)
    print("\nTop losers:\n", losers_df)
