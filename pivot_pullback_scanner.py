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
3. After 09:30, wait for price to come back to the pivot itself (no
   tolerance): BUY a candle low at or below it, SELL a candle high at or
   above it.
4. From that touch candle onward, the first GREEN candle closing above the
   pivot (BUY: entry = its high, SL = its low) or RED candle closing below
   it (SELL: entry = its low, SL = its high) is the signal. The SL sits
   SL_BUFFER_PCT beyond that candle (BUY below its low, SELL above its
   high) so a wick just past the candle doesn't stop the trade out.

Later candles then decide the status: Signal (entry not yet hit) ->
Triggered (price crossed the entry) -> SL Hit / Target Hit (1:5 R:R);
Invalidated if the SL side breaks before entry. Only
fully-closed 5-min candles are used, so a candle still forming is never
mistaken for a signal.

Entries only count until ENTRY_CUTOFF (10:15): the trigger must happen in
a candle starting before it. After that, a setup not yet triggered (or
still waiting) is "Expired" and no new setups are looked for; trades
already triggered keep being tracked to SL / target.

One trade a day, picked when its signal candle closes (so an order can
be placed before it triggers): the earliest signal, same candle ->
highest first-15-min traded value (over 21 Sep - 5 Oct 2026 that beat
smaller-Risk%-first, +6.2R vs +3.9R: ADANIPOWER, not NESTLEIND's SL hit,
on 5 Oct). If the pick is Invalidated before entry, the next setup still
pending at that point takes over. Every other stock is "Not picked".
Breadth is checked again at each signal candle's close (every stock's
close then vs its previous close): a setup is only picked if the day's
side still leads at that moment.

Per stock: one Dhan intraday call for today's 5-min candles, plus the
previous session's high/low/close from Dhan's DAILY candles (cached for
the day). Not from the 5-min candles: Dhan's intraday data stops at the
15:10 candle and has no closing-auction price, so a pivot built from it
was wrong whenever the last 20 minutes made the high/low (DLF on 30 Sep:
real pivot 667.00, 5-min-based 664.03). The intraday endpoint is
rate-limited (DH-904), so calls are throttled like first_minute_movers.py.
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
TARGET_R_MULTIPLE = 5
SL_BUFFER_PCT = 0.30
ENTRY_CUTOFF = "10:15"

MAX_WORKERS = 3
SUBMIT_STAGGER_SECONDS = 0.4
RETRY_PASS_DELAY_SECONDS = 2

logger = logging.getLogger(__name__)


def load_universe():
    obj = boto3.client("s3", region_name=AWS_REGION).get_object(Bucket=BUCKET, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name", "Instrument ID"])
    return [(str(r["Stock Name"]).strip().upper(), int(r["Instrument ID"])) for _, r in df.iterrows()]


def today_candles(df, date_str, now=None):
    """`date_str`'s closed 5-min candles, or None if the first 15 minutes
    aren't complete yet. `now` (IST datetime) drops the still-forming
    candle; None = all candles closed."""
    today = df[df["time"].dt.strftime("%Y-%m-%d") == date_str].reset_index(drop=True)
    if now is not None and not today.empty:
        closed = today["time"] + pd.Timedelta(minutes=INTERVAL_MINUTES) <= now
        today = today[closed].reset_index(drop=True)
    return today if len(today) >= FIRST_WINDOW_CANDLES else None


def breadth_move(df, prev, date_str, now=None):
    """+1 advance / -1 decline / 0 unchanged at the end of the first 15
    minutes vs the previous session's official close, or None without
    data. `prev` = {"high", "low", "close"} of the previous session."""
    today = today_candles(df, date_str, now)
    if today is None or prev is None:
        return None
    prev_close = prev["close"]
    close15 = today["close"].iloc[FIRST_WINDOW_CANDLES - 1]
    return int(close15 > prev_close) - int(close15 < prev_close)


def breadth_by_candle(candles, date_str, now=None):
    """{"HH:MM": (advances, declines)} for every closed 5-min candle of
    `date_str` — each stock's candle close vs its previous session close,
    the same comparison as the 09:30 breadth_move. `candles` = iterable of
    (5-min df, prev session dict)."""
    counts = {}
    for df, prev in candles:
        today = today_candles(df, date_str, now)
        if today is None or prev is None:
            continue
        for t, close in zip(today["time"].dt.strftime("%H:%M"), today["close"]):
            adv, dec = counts.get(t, (0, 0))
            counts[t] = (adv + (close > prev["close"]), dec + (close < prev["close"]))
    return counts


def compute_signal(df, prev, date_str, side="BUY", now=None):
    """Pure function: `date_str`'s 5-min candles (time [IST], open, high,
    low, close) + the previous session's daily {"high", "low", "close"}
    -> result dict,
    or None if the stock doesn't pass the first-15-minute pivot cross for
    `side` ("BUY" or "SELL").

    SELL runs the BUY logic on negated prices (high and low swap, so every
    comparison flips: cross below, red candle, entry at its low, SL at its
    high) — one code path for both sides, so they can't drift apart.
    """
    today = today_candles(df, date_str, now)
    if today is None or prev is None:
        return None

    # Traded value (volume x close) of the first 15 minutes, in crore —
    # the same-candle tiebreak in pick_daily_trade. Taken before the
    # SELL-side price negation below.
    first_real = today.iloc[:FIRST_WINDOW_CANDLES]
    value15_cr = round(float((first_real["volume"] * first_real["close"]).sum()) / 1e7, 2)

    sign = 1 if side == "BUY" else -1
    prev_high, prev_low, prev_close = prev["high"], prev["low"], prev["close"]
    if sign < 0:
        prev_high, prev_low, prev_close = -prev["low"], -prev["high"], -prev["close"]
        today = today.assign(open=-today["open"], high=-today["low"], low=-today["high"], close=-today["close"])

    def px(value):  # back to real prices for output
        return round(float(sign * value), 2)

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
        "15m Value Cr": value15_cr,
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
    last_end = (today["time"].iloc[-1] + pd.Timedelta(minutes=INTERVAL_MINUTES)).strftime("%H:%M")
    cutoff_passed = last_end >= ENTRY_CUTOFF
    # Setup search (touch + signal candle) only before the cutoff — a
    # signal at/after it could never trigger in time.
    early = after[after["time"].dt.strftime("%H:%M") < ENTRY_CUTOFF]
    touches = early.index[early["low"] <= pivot]
    if len(touches) == 0:
        if cutoff_passed:
            result["Status"] = "Expired"
        return result
    touch_idx = touches[0]
    result["Touch Time"] = after.at[touch_idx, "time"].strftime("%H:%M")
    result["Status"] = "Waiting Green Candle" if sign > 0 else "Waiting Red Candle"

    candidates = early.loc[touch_idx:]
    candidates = candidates[(candidates["close"] > candidates["open"]) & (candidates["close"] > pivot)]
    if candidates.empty:
        if cutoff_passed:
            result["Status"] = "Expired"
        return result
    sig_idx = candidates.index[0]
    sig = after.loc[sig_idx]
    entry, sl = float(sig["high"]), float(sig["low"])
    sl -= abs(sl) * SL_BUFFER_PCT / 100  # below the low (BUY) / above the high (SELL, negated)
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
            if t >= ENTRY_CUTOFF:
                result["Status"], result["Exit Time"] = "Expired", ENTRY_CUTOFF
                break
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
    if result["Status"] == "Signal" and cutoff_passed:
        result["Status"], result["Exit Time"] = "Expired", ENTRY_CUTOFF
    return result


def previous_session(security_id, date_str):
    """{"high", "low", "close"} of the last daily candle before `date_str`,
    or None. The range is fixed per date, so get_historical_daily's cache
    serves every 5-minute run of the day from one call per stock."""
    start = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
    daily = dhan_connector.get_historical_daily(security_id, start, date_str)
    if daily is None or daily.empty:
        return None
    prior = daily[daily["date"] < date_str]
    if prior.empty:
        return None
    last = prior.iloc[-1]
    return {"high": float(last["high"]), "low": float(last["low"]), "close": float(last["close"])}


def _fetch_one(symbol, security_id, date_str):
    """-> (today's 5-min candles, previous session dict), or None."""
    try:
        prev = previous_session(security_id, date_str)
        df = dhan_connector.get_intraday_candles(
            # From 09:00, not 09:15: Dhan treats the start as exclusive and
            # would drop the 09:15 candle.
            security_id, f"{date_str} 09:00:00", f"{date_str} 15:30:00", interval=INTERVAL_MINUTES
        )
    except Exception as exc:
        logger.warning("%s skipped - %s", symbol, exc)
        return None
    if prev is None or df.empty:
        return None
    return df, prev


SKIPPED = "Not picked"
STATUS_ORDER = [
    "Triggered", "Signal", "Target Hit", "SL Hit", "Invalidated",
    "Waiting Green Candle", "Waiting Red Candle", "Waiting Pullback", "Expired", SKIPPED,
]


def pick_daily_trade(df, locked=()):
    """The day's one trade, chosen at signal time: earliest Signal Time,
    same candle -> highest "15m Value Cr". A pick Invalidated before entry
    hands over to the next setup that was still pending then (not yet
    triggered or invalidated). `locked` = symbols already picked earlier
    today, kept first in that order so a re-run (e.g. a stock missing from
    an earlier fetch) can't swap a pick that was already alerted. Every
    stock not picked becomes SKIPPED. -> (df, [picked symbols in order])."""
    if df.empty or "Signal Time" not in df:
        return df, []
    locked = list(locked)
    sig = df[df["Signal Time"].notna()]
    if "Breadth OK" in df:
        # A setup whose signal candle closed with breadth against the
        # day's side isn't tradeable (already-alerted picks stay).
        sig = sig[sig["Breadth OK"].fillna(False).astype(bool) | sig["Stock Name"].isin(locked)]
    order = sorted(sig.index, key=lambda i: (
        locked.index(sig.at[i, "Stock Name"]) if sig.at[i, "Stock Name"] in locked else len(locked),
        sig.at[i, "Signal Time"],
        -sig.at[i, "15m Value Cr"],
    ))
    picks, handover = [], None
    for i in order:
        row = df.loc[i]
        if handover is not None:
            if pd.notna(row["Trigger Time"]) and row["Trigger Time"] <= handover:
                continue  # already past its entry before it could be alerted
            if row["Status"] == "Invalidated" and row["Exit Time"] <= handover:
                continue
        picks.append(i)
        if row["Status"] != "Invalidated":
            break
        handover = row["Exit Time"]
    df = df.copy()
    df.loc[~df.index.isin(picks), "Status"] = SKIPPED
    return df, [df.at[i, "Stock Name"] for i in picks]


def get_pivot_pullback_setups(date_str=None, save=True, locked_picks=()):
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
            fetched = future.result()
            if fetched is not None:
                candles[(symbol, sid)] = fetched

    # Stocks that still hit Dhan's rate limit after _fetch_one's own
    # retries (seen live: ~4 of 100 when the breakout bot is also calling
    # Dhan) get one slower, one-at-a-time pass — a skipped stock both
    # misses its signals and skews the breadth count.
    missed = [(symbol, sid) for symbol, sid in universe if (symbol, sid) not in candles]
    for symbol, sid in missed:
        time.sleep(RETRY_PASS_DELAY_SECONDS)
        fetched = _fetch_one(symbol, sid, date_str)
        if fetched is not None:
            candles[(symbol, sid)] = fetched
    if missed:
        logger.info("Retry pass recovered %s of %s skipped stocks", sum(k in candles for k in missed), len(missed))

    moves = [m for m in (breadth_move(df, prev, date_str, cutoff) for df, prev in candles.values()) if m is not None]
    advances, declines = moves.count(1), moves.count(-1)
    side = "BUY" if advances > declines else "SELL"
    breadth = {"advances": advances, "declines": declines, "unchanged": moves.count(0), "side": side}
    logger.info("Breadth at 09:30 | adv=%s dec=%s -> %s side", advances, declines, side)

    rows = []
    if moves:
        for (symbol, sid), (df, prev) in candles.items():
            result = compute_signal(df, prev, date_str, side, cutoff)
            if result is not None:
                rows.append({"Stock Name": symbol, "Security ID": sid, **result})

    # Breadth is re-checked when each signal candle closes: the day's
    # side (fixed at 09:30) must still lead then, or that setup is skipped.
    by_candle = breadth_by_candle(candles.values(), date_str, cutoff)
    for row in rows:
        if row["Signal Time"]:
            adv, dec = by_candle.get(row["Signal Time"], (0, 0))
            row["Signal Breadth"] = f"{adv} adv / {dec} dec"
            row["Breadth OK"] = (adv > dec) == (side == "BUY")

    df, picks = pick_daily_trade(pd.DataFrame(rows), locked_picks)
    breadth["picks"] = picks
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
