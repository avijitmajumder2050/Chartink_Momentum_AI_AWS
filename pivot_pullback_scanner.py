"""Pivot cross -> pullback -> 5-min candle scanner, buy OR sell side by
market breadth.

Universe: uploads/nifty_mapping.csv in the new-dhan-trading-data bucket
(Stock Name, Instrument ID), read from that bucket explicitly rather than
through chart_connector's bucket probe, which prefers dhan-trading-data.

Market breadth picks the side for the whole day: across the same
universe, advances vs declines at 09:30 (first-15-min close vs previous
session close). Advances > declines -> BUY setups only, otherwise SELL
setups only. Fixed at 09:30 so the side doesn't flip mid-session.

Per stock, for one trading day (SELL is the exact mirror of BUY):

1. Pivot = classic floor pivot from the previous session: (H + L + C) / 3.
2. First 15 minutes (09:15-09:30, the first three 5-min candles combined)
   must CROSS the pivot: BUY open below / close above, SELL the reverse.
3. After 09:30, wait for price to come back to the pivot: BUY a candle low
   at or within TOUCH_TOLERANCE_PCT above it, SELL a candle high at or
   within that tolerance below it.
4. From that touch candle onward, the first GREEN candle closing above the
   pivot (BUY: entry = its high, SL = its low) or RED candle closing below
   it (SELL: entry = its low, SL = its high) is the signal.

Later candles then decide the status: Signal (entry not yet hit) ->
Triggered (price crossed the entry) -> SL Hit / Target Hit (1:2 R:R,
informational only); Invalidated if the SL side breaks before entry. Only
fully-closed 5-min candles are used, so a candle still forming is never
mistaken for a signal.

One Dhan intraday call per stock (5-min candles from a week back through
now) gives both the previous session's HLC and today's candles. That
endpoint is rate-limited (DH-904), so calls are throttled like
first_minute_movers.py.
"""

import argparse
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import boto3
import pandas as pd
import pytz

from connectors import dhan_connector

IST = pytz.timezone("Asia/Kolkata")

BUCKET = "new-dhan-trading-data"
MAPPING_KEY = "uploads/nifty_mapping.csv"
OUTPUT_KEY = "uploads/pivot_pullback_scan.csv"
AWS_REGION = "ap-south-1"

INTERVAL_MINUTES = 5
FIRST_WINDOW_CANDLES = 3  # 3 x 5 min = the first 15 minutes
# "Back to pivot" — the candle may stop this far short of the pivot (as a
# % of pivot) and still count as a touch; reaching or crossing it always
# counts.
TOUCH_TOLERANCE_PCT = 0.10
TARGET_R_MULTIPLE = 2

MAX_WORKERS = 3
SUBMIT_STAGGER_SECONDS = 0.4

logger = logging.getLogger(__name__)


def load_universe():
    obj = boto3.client("s3", region_name=AWS_REGION).get_object(Bucket=BUCKET, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name", "Instrument ID"])
    return [(str(r["Stock Name"]).strip().upper(), int(r["Instrument ID"])) for _, r in df.iterrows()]


def split_session(df, date_str, now=None):
    """-> (prev_day candles, today's closed candles), or None if either is
    missing or the first 15 minutes aren't complete yet. `now` (IST
    datetime) drops the still-forming candle; None = all candles closed."""
    day = df["time"].dt.strftime("%Y-%m-%d")
    prior = df[day < date_str]
    today = df[day == date_str].reset_index(drop=True)
    if now is not None and not today.empty:
        closed = today["time"] + pd.Timedelta(minutes=INTERVAL_MINUTES) <= now
        today = today[closed].reset_index(drop=True)
    if prior.empty or len(today) < FIRST_WINDOW_CANDLES:
        return None
    prev_day = prior[day[prior.index] == day[prior.index].iloc[-1]]
    return prev_day, today


def breadth_move(df, date_str, now=None):
    """+1 advance / -1 decline / 0 unchanged at the end of the first 15
    minutes vs the previous session close, or None without data."""
    parts = split_session(df, date_str, now)
    if parts is None:
        return None
    prev_day, today = parts
    prev_close = prev_day["close"].iloc[-1]
    close15 = today["close"].iloc[FIRST_WINDOW_CANDLES - 1]
    return int(close15 > prev_close) - int(close15 < prev_close)


def compute_signal(df, date_str, side="BUY", now=None):
    """Pure function: 5-min candles (time [IST], open, high, low, close)
    spanning at least the previous session and `date_str` -> result dict,
    or None if the stock doesn't pass the first-15-minute pivot cross for
    `side` ("BUY" or "SELL").

    SELL runs the BUY logic on negated prices (high and low swap, so every
    comparison flips: cross below, red candle, entry at its low, SL at its
    high) — one code path for both sides, so they can't drift apart.
    """
    parts = split_session(df, date_str, now)
    if parts is None:
        return None
    prev_day, today = parts

    sign = 1 if side == "BUY" else -1
    if sign < 0:
        prev_day = prev_day.assign(high=-prev_day["low"], low=-prev_day["high"], close=-prev_day["close"])
        today = today.assign(open=-today["open"], high=-today["low"], low=-today["high"], close=-today["close"])

    def px(value):  # back to real prices for output
        return round(float(sign * value), 2)

    prev_high, prev_low = prev_day["high"].max(), prev_day["low"].min()
    prev_close = prev_day["close"].iloc[-1]
    pivot = (prev_high + prev_low + prev_close) / 3

    first = today.iloc[:FIRST_WINDOW_CANDLES]
    open15, close15 = first["open"].iloc[0], first["close"].iloc[-1]
    if not (open15 < pivot < close15):
        return None

    level_up, level_down = 2 * pivot - prev_low, 2 * pivot - prev_high
    result = {
        "Side": side,
        "Pivot": px(pivot),
        "R1": px(level_up if sign > 0 else level_down),
        "S1": px(level_down if sign > 0 else level_up),
        "15m Open": px(open15),
        "15m Close": px(close15),
        "Status": "Waiting Pullback",
        "Touch Time": None,
        "Signal Time": None,
        "Entry": None,
        "SL": None,
        "Risk %": None,
        "Target": None,
        "Trigger Time": None,
        "Exit Time": None,
        "LTP": px(today["close"].iloc[-1]),
    }

    after = today.iloc[FIRST_WINDOW_CANDLES:].reset_index(drop=True)
    touch_level = pivot + abs(pivot) * TOUCH_TOLERANCE_PCT / 100
    touches = after.index[after["low"] <= touch_level]
    if len(touches) == 0:
        return result
    touch_idx = touches[0]
    result["Touch Time"] = after.at[touch_idx, "time"].strftime("%H:%M")
    result["Status"] = "Waiting Green Candle" if sign > 0 else "Waiting Red Candle"

    candidates = after.iloc[touch_idx:]
    candidates = candidates[(candidates["close"] > candidates["open"]) & (candidates["close"] > pivot)]
    if candidates.empty:
        return result
    sig_idx = candidates.index[0]
    sig = after.loc[sig_idx]
    entry, sl = float(sig["high"]), float(sig["low"])
    risk = entry - sl
    target = entry + TARGET_R_MULTIPLE * risk
    result.update({
        "Status": "Signal",
        "Signal Time": sig["time"].strftime("%H:%M"),
        "Entry": px(entry),
        "SL": px(sl),
        "Risk %": round(risk / abs(entry) * 100, 2) if entry else None,
        "Target": px(target),
    })

    # Entry is a stop order beyond the signal candle; until it fills, a
    # break of the SL side first means the setup failed without a trade.
    for _, c in after.iloc[sig_idx + 1:].iterrows():
        t = c["time"].strftime("%H:%M")
        if result["Status"] == "Signal":
            if c["high"] > entry:
                result["Status"], result["Trigger Time"] = "Triggered", t
                if c["low"] <= sl:  # same candle: assume the worse outcome
                    result["Status"], result["Exit Time"] = "SL Hit", t
                    break
            elif c["low"] < sl:
                result["Status"], result["Exit Time"] = "Invalidated", t
                break
        elif result["Status"] == "Triggered":
            if c["low"] <= sl:
                result["Status"], result["Exit Time"] = "SL Hit", t
                break
            if c["high"] >= target:
                result["Status"], result["Exit Time"] = "Target Hit", t
                break
    return result


def _fetch_one(symbol, security_id, date_str):
    start = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        return dhan_connector.get_intraday_candles(
            security_id, f"{start} 09:15:00", f"{date_str} 15:30:00", interval=INTERVAL_MINUTES
        )
    except Exception as exc:
        logger.warning("%s skipped - %s", symbol, exc)
        return None


STATUS_ORDER = [
    "Triggered", "Signal", "Target Hit", "SL Hit", "Invalidated",
    "Waiting Green Candle", "Waiting Red Candle", "Waiting Pullback",
]


def get_pivot_pullback_setups(date_str=None, save=True):
    """-> (DataFrame, breadth dict). Breadth (advances/declines at 09:30)
    picks BUY or SELL; the DataFrame holds every stock whose first 15
    minutes crossed the pivot on that side, each with its setup status."""
    now = datetime.now(IST)
    is_today = date_str is None or date_str == now.strftime("%Y-%m-%d")
    date_str = date_str or now.strftime("%Y-%m-%d")
    cutoff = now if is_today else None
    universe = load_universe()
    logger.info("Pivot pullback scan %s | %s stocks", date_str, len(universe))

    candles = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = []
        for symbol, sid in universe:
            futures.append((symbol, sid, pool.submit(_fetch_one, symbol, sid, date_str)))
            time.sleep(SUBMIT_STAGGER_SECONDS)
        for symbol, sid, future in futures:
            df = future.result()
            if df is not None and not df.empty:
                candles[(symbol, sid)] = df

    moves = [m for m in (breadth_move(df, date_str, cutoff) for df in candles.values()) if m is not None]
    advances, declines = moves.count(1), moves.count(-1)
    side = "BUY" if advances > declines else "SELL"
    breadth = {"advances": advances, "declines": declines, "unchanged": moves.count(0), "side": side}
    logger.info("Breadth at 09:30 | adv=%s dec=%s -> %s side", advances, declines, side)

    rows = []
    if moves:
        for (symbol, sid), df in candles.items():
            result = compute_signal(df, date_str, side, cutoff)
            if result is not None:
                rows.append({"Stock Name": symbol, "Security ID": sid, **result})

    df = pd.DataFrame(rows)
    if not df.empty:
        df["_order"] = df["Status"].map(STATUS_ORDER.index)
        df = df.sort_values(["_order", "Signal Time", "Stock Name"]).drop(columns="_order").reset_index(drop=True)
        df["Breadth"] = f"{advances} adv / {declines} dec"
        df["Scan Time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        df["Date"] = date_str

    logger.info("Pivot cross stocks: %s | signals: %s", len(df), int(df["Entry"].notna().sum()) if not df.empty else 0)

    if save and not df.empty:
        body = df.to_csv(index=False).encode("utf-8")
        boto3.client("s3", region_name=AWS_REGION).put_object(
            Bucket=BUCKET, Key=OUTPUT_KEY, Body=body, ContentType="text/csv"
        )
        logger.info("Saved to s3://%s/%s", BUCKET, OUTPUT_KEY)
    return df, breadth


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pivot cross -> pullback scanner, side by market breadth")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--no-save", action="store_true", help="don't write the result to S3")
    args = parser.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    result_df, breadth = get_pivot_pullback_setups(args.date, save=not args.no_save)
    print(breadth)
    print(result_df)
