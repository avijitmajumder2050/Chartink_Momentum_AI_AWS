"""Opening base breakout scanner — the BSE pattern of 26 Oct 2026.

Universe: uploads/fno_mapping.csv in the new-dhan-trading-data bucket
(the F&O stock list: Stock Name, Instrument ID, Lot Size).

Per stock, from the first four 5-min candles (09:15-09:35):

1. C1 opening drive: green, closing in the top 30% of its range, with a
   body of at least 60% of the range.
2. C2 and C3 pull back inside C1: high no higher than C1's, low above C1's.
3. C4 makes a higher low (above the lower of C2/C3) and its high reaches
   C1's high (within C4_NEAR_PCT).
4. The whole 4-candle range is at most MAX_RANGE_PCT of price.
5. C1 traded at least MIN_C1_VALUE_CR (close x volume) — the one filter
   that helped in both halves of the backtest (see below).

BSE 26 Oct: C1 3213 -> 3251 (high 3258.5), C2/C3 held 3236.6/3231.4, C4
low 3243.3 high 3260.0 -> broke 3260 at 09:37 and hit 5R by 09:52.

Entry = break of the 4-candle high, only from 09:35 until ENTRY_CUTOFF
(10:00); SL = C4 low; target TARGET_R_MULTIPLE x risk; the SL trails up by
TRAIL_R x risk each time price moves that far (Dhan's trailing jump, as
trading-bot-algo places it); anything still open exits at TIME_EXIT.
Statuses: Waiting Breakout -> Triggered -> Target Hit / SL Hit / Trailed
Out / Time Exit; Expired if no breakout by the cutoff.

Backtest (210 F&O stocks, 1-min candles, 15 Jun - 23 Oct 2026), first
breakout of each day: without the value filter 54 trades +1.8R (+0.03R
a trade, worst run -6.5R); with C1 >= Rs 5 cr 41 trades +18.0R (+0.44R,
44% win, worst run -2.5R) — +13.5R on the older 38 days it was chosen on
and +4.5R on the newer 16 it wasn't. The trail is what makes it pay: with
no trail the unfiltered one-a-day trades were -4.8R over the last 30 days.

One Dhan intraday call per stock for today's 1-min candles (the backtest
used 1-min too, so live statuses match it), throttled like the pivot
scanner — the endpoint is rate-limited (DH-904).
"""

import argparse
import io
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import boto3
import pandas as pd
import pytz

from connectors import dhan_connector

IST = pytz.timezone("Asia/Kolkata")

BUCKET = "new-dhan-trading-data"
MAPPING_KEY = "uploads/fno_mapping.csv"
OUTPUT_KEY = "uploads/opening_base_scan.csv"
AWS_REGION = "ap-south-1"

BASE_CANDLES = 4  # 4 x 5 min = 09:15-09:35
BASE_END = "09:35"
ENTRY_CUTOFF = "10:00"
TIME_EXIT = "15:05"
MAX_RANGE_PCT = 2.5
MIN_C1_VALUE_CR = 5
C4_NEAR_PCT = 0.2
TARGET_R_MULTIPLE = 5
TRAIL_R = 0.5

MAX_WORKERS = 3
SUBMIT_STAGGER_SECONDS = 0.4
RETRY_PASS_DELAY_SECONDS = 2

STATUS_ORDER = ["Triggered", "Waiting Breakout", "Target Hit", "Trailed Out", "Time Exit", "SL Hit", "Expired"]

logger = logging.getLogger(__name__)


def load_universe():
    obj = boto3.client("s3", region_name=AWS_REGION).get_object(Bucket=BUCKET, Key=MAPPING_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name", "Instrument ID"])
    return [(str(r["Stock Name"]).strip().upper(), int(r["Instrument ID"])) for _, r in df.iterrows()]


def base_setup(five):
    """First four 5-min candles -> {"High", "Low", "SL", "C1 Value Cr"}
    if they form the opening base, else None."""
    c1, c2, c3, c4 = (five.iloc[i] for i in range(BASE_CANDLES))
    r1 = c1.high - c1.low
    if r1 <= 0 or c1.close <= c1.open:
        return None
    if (c1.close - c1.low) / r1 < 0.7 or (c1.close - c1.open) / r1 < 0.6:
        return None
    if any(c.high > c1.high or c.low <= c1.low for c in (c2, c3)):
        return None
    if c4.low <= min(c2.low, c3.low) or c4.high < c1.high * (1 - C4_NEAR_PCT / 100):
        return None
    high = float(five.high.iloc[:BASE_CANDLES].max())
    low = float(five.low.iloc[:BASE_CANDLES].min())
    if (high - low) / high * 100 > MAX_RANGE_PCT:
        return None
    value_cr = c1.close * c1.volume / 1e7
    if value_cr < MIN_C1_VALUE_CR:
        return None
    return {"High": high, "Low": low, "SL": float(c4.low), "C1 Value Cr": round(float(value_cr), 2)}


def compute_signal(minutes, now=None):
    """Pure function: one day's 1-min candles (time [IST], open, high,
    low, close, volume) -> result dict, or None if the opening base didn't
    form. `now` drops the still-forming minute; None = all closed."""
    if now is not None:
        minutes = minutes[minutes["time"] + pd.Timedelta(minutes=1) <= now]
    minutes = minutes.set_index("time")
    five = minutes.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    if len(five) < BASE_CANDLES or five.index[0].strftime("%H:%M") != "09:15":
        return None
    if five.index[BASE_CANDLES - 1].strftime("%H:%M") != "09:30" or minutes.index[-1].strftime("%H:%M") < "09:34":
        return None  # the base isn't complete yet
    setup = base_setup(five)
    if setup is None:
        return None

    hm = minutes.index.strftime("%H:%M")
    entry = round(setup["High"] + 0.05, 2)
    risk = entry - setup["SL"]
    result = {
        "Status": "Waiting Breakout", "Entry": entry, "SL": setup["SL"],
        "Risk %": round(risk / entry * 100, 2), "Target": round(entry + TARGET_R_MULTIPLE * risk, 2),
        "Trigger Time": None, "Exit Time": None, "Exit Price": None, "R": None,
        "Base High": setup["High"], "Base Low": setup["Low"],
        "Range %": round((setup["High"] - setup["Low"]) / setup["High"] * 100, 2),
        "C1 Value Cr": setup["C1 Value Cr"], "LTP": float(minutes.close.iloc[-1]),
    }
    window = minutes[(hm >= BASE_END) & (hm < ENTRY_CUTOFF)]
    hit = window[window.high > setup["High"]]
    if hit.empty:
        if hm[-1] >= ENTRY_CUTOFF:
            result["Status"] = "Expired"
        return result

    t = hit.index[0]
    fill = max(float(hit.open.iloc[0]), entry)  # a gap through the high fills at the open
    risk = fill - setup["SL"]
    result.update({"Status": "Triggered", "Trigger Time": t.strftime("%H:%M"), "Entry": round(fill, 2),
                   "Risk %": round(risk / fill * 100, 2), "Target": round(fill + TARGET_R_MULTIPLE * risk, 2)})
    stop, top, jump = setup["SL"], fill, TRAIL_R * risk
    after = minutes[minutes.index > t]
    for when, c in after.iterrows():
        at = when.strftime("%H:%M")
        if at > TIME_EXIT:
            break
        if c.low <= stop:
            status = "SL Hit" if stop == setup["SL"] else "Trailed Out"
            result.update(Status=status, **{"Exit Time": at, "Exit Price": round(stop, 2), "R": round((stop - fill) / risk, 2)})
            return result
        if c.high >= result["Target"]:
            result.update(Status="Target Hit", **{"Exit Time": at, "Exit Price": result["Target"], "R": float(TARGET_R_MULTIPLE)})
            return result
        top = max(top, c.high)
        stop = max(stop, setup["SL"] + math.floor((top - fill) / jump) * jump)
    last = float(after[after.index.strftime("%H:%M") <= TIME_EXIT].close.iloc[-1]) if not after.empty else fill
    if hm[-1] >= TIME_EXIT:
        result.update(Status="Time Exit", **{"Exit Time": TIME_EXIT, "Exit Price": round(last, 2)})
    result["R"] = round((last - fill) / risk, 2)
    result["Trail SL"] = round(stop, 2)
    return result


def _fetch_one(symbol, security_id, date_str):
    try:
        # From 09:00, not 09:15: Dhan treats the start as exclusive.
        return dhan_connector._fetch_intraday_minute(security_id, f"{date_str} 09:00:00", f"{date_str} 15:30:00", interval=1)
    except Exception as exc:
        logger.warning("%s skipped - %s", symbol, exc)
        return None


def pick_daily_trade(df):
    """The day's one trade: first breakout, same minute -> highest C1
    traded value (how the backtest's one-a-day line was counted)."""
    trig = df[df["Trigger Time"].notna()] if not df.empty else df
    if trig.empty:
        return None
    return trig.sort_values(["Trigger Time", "C1 Value Cr"], ascending=[True, False]).iloc[0]["Stock Name"]


def get_opening_base_setups(date_str=None, save=True):
    """-> (DataFrame of every stock that formed the base today, summary)."""
    now = datetime.now(IST)
    is_today = date_str is None or date_str == now.strftime("%Y-%m-%d")
    date_str = date_str or now.strftime("%Y-%m-%d")
    cutoff = now if is_today else None
    universe = load_universe()
    logger.info("Opening base scan %s | %s stocks", date_str, len(universe))

    candles = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = []
        for symbol, sid in universe:
            futures.append((symbol, sid, pool.submit(_fetch_one, symbol, sid, date_str)))
            time.sleep(SUBMIT_STAGGER_SECONDS)
        for symbol, sid, future in futures:
            if (fetched := future.result()) is not None:
                candles[(symbol, sid)] = fetched
    for symbol, sid in [k for k in universe if k not in candles]:
        time.sleep(RETRY_PASS_DELAY_SECONDS)
        if (fetched := _fetch_one(symbol, sid, date_str)) is not None:
            candles[(symbol, sid)] = fetched

    rows = []
    for (symbol, sid), minutes in candles.items():
        if minutes.empty:
            continue
        day = minutes[minutes["time"].dt.strftime("%Y-%m-%d") == date_str].reset_index(drop=True)
        if not day.empty and (result := compute_signal(day, cutoff)) is not None:
            rows.append({"Stock Name": symbol, "Security ID": sid, **result})

    df = pd.DataFrame(rows)
    summary = {"scanned": len(candles), "universe": len(universe), "pick": None}
    if not df.empty:
        summary["pick"] = pick_daily_trade(df)
        df["_order"] = df["Status"].map(STATUS_ORDER.index)
        df = df.sort_values(["_order", "Trigger Time", "C1 Value Cr"], ascending=[True, True, False]).drop(columns="_order").reset_index(drop=True)
        df["Scan Time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        df["Date"] = date_str
    logger.info("Opening base stocks: %s | pick: %s", len(df), summary["pick"])

    if save and not df.empty:
        boto3.client("s3", region_name=AWS_REGION).put_object(
            Bucket=BUCKET, Key=OUTPUT_KEY, Body=df.to_csv(index=False).encode("utf-8"), ContentType="text/csv"
        )
    return df, summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Opening base (BSE pattern) breakout scanner, F&O stocks")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--no-save", action="store_true", help="don't write the result to S3")
    args = parser.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    result_df, summary = get_opening_base_setups(args.date, save=not args.no_save)
    print(summary)
    print(result_df)
