"""EMA 10/20 breakout scanner — Dhan-based, alongside this file's Chartink-
based siblings (chartink_momentum.py, chartink_stoch_backtest.py).

Same condition as the Chart Wall's browser-side EMA cross filter
(templates/chart_wall.html -> detectEmaCross()): close crosses above EMA10
or EMA20, with EMA10 > EMA20 > EMA50 aligned on the latest candle — kept
identical on purpose so the scanner and the Chart Wall agree on what an
"EMA cross" is.

Reads through connectors/chart_connector.py rather than connectors/
dhan_connector.py: dhan_connector.py's interface moved to security-ID
resolution + historical candles only and no longer exposes S3 mapping/EOD
reads or batched live quotes, while chart_connector.py already has all of
that (get_watchlist_stocks_cached() for the universe + Market Cap/EPS
Strength/Price Strength/Setup_Case, get_ohlcv() for EOD bars merged with
today's live quote). Using the exact same get_ohlcv() the Chart Wall's
/api/chart/data endpoint calls means this scanner and the browser filter
read identical bars, not just the same formula.

Also requires EPS Strength >= 80 and Price Strength >= 80 (on top of the
market-cap/volume filters) — a condition Dhan_MCP's own scanner doesn't
apply, so matches are written to this project's own S3 output key
(uploads/chartink_ema_momentum_EOD.csv) rather than Dhan_MCP's
uploads/ema_momentum_EOD.csv — two writers with different column sets
should not share one file.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import pytz

from connectors import chart_connector

IST = pytz.timezone("Asia/Kolkata")
OUTPUT_KEY = "uploads/chartink_ema_momentum_EOD.csv"

logger = logging.getLogger(__name__)


def _compute_ema_signal(bars):
    """Pure function: bars (list of dicts, ascending by date, with open/
    high/low/close/volume, at least 50 rows — chart_connector.get_ohlcv()'s
    shape) -> a result dict, or None if there isn't enough history.

    Kept separate from the per-stock loop in get_ema_breakout_matches() so
    it's unit-testable against a synthetic bar list without mocking S3 or
    Dhan.
    """

    if len(bars) < 50:
        return None

    df = pd.DataFrame(bars[-120:])
    df["ema10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    cross_ema10 = prev["close"] <= prev["ema10"] and latest["close"] > latest["ema10"]
    cross_ema20 = prev["close"] <= prev["ema20"] and latest["close"] > latest["ema20"]
    aligned = latest["ema10"] > latest["ema20"] > latest["ema50"]

    return {
        "matched": (cross_ema10 or cross_ema20) and aligned,
        "open": round(float(latest["open"]), 2),
        "close": round(float(latest["close"]), 2),
        "high": round(float(latest["high"]), 2),
        "low": round(float(latest["low"]), 2),
        "volume": float(latest["volume"]),
    }


def get_ema_breakout_matches():
    logger.info("EMA breakout scan started")

    scan_time = datetime.now(IST)
    scan_time_str = scan_time.strftime("%Y-%m-%d %H:%M:%S")

    stocks = chart_connector.get_watchlist_stocks_cached()
    mapping = chart_connector.get_symbol_mapping()
    logger.info("Watchlist loaded | Total stocks: %s", len(stocks))

    matched = []

    for stock in stocks:
        symbol = stock["symbol"]
        market_cap = stock["marketCap"]
        eps_strength = stock["epsStrength"]
        price_strength = stock["priceStrength"]
        setup_case = stock["setupCase"]

        if market_cap is None or eps_strength is None or price_strength is None:
            continue

        try:
            bars = chart_connector.get_ohlcv(symbol)
        except Exception as exc:
            logger.warning("%s skipped - no chart data (%s)", symbol, exc)
            continue

        signal = _compute_ema_signal(bars)
        if signal is None:
            logger.warning("%s skipped - not enough candles", symbol)
            continue

        cond_filters = (
            market_cap > 500
            and signal["volume"] > 70000
            and eps_strength >= 80
            and price_strength >= 80
        )

        logger.info(
            "%s | matched=%s | Align/Cross ok=%s | MCap=%s | Vol=%s | EPS=%s | PriceStr=%s",
            symbol, signal["matched"] and cond_filters, signal["matched"], market_cap, signal["volume"],
            eps_strength, price_strength,
        )

        if signal["matched"] and cond_filters:
            matched.append({
                "Stock Name": symbol,
                "Security ID": mapping.get(symbol),
                "Market Cap": market_cap,
                "Open": signal["open"],
                "Price": signal["close"],
                "High": signal["high"],
                "Low": signal["low"],
                "EPS Strength": eps_strength,
                "Price Strength": price_strength,
                "Setup_Case": setup_case,
                "Scan Time": scan_time_str,
            })

    logger.info("Total matched stocks today: %s", len(matched))

    today_df = pd.DataFrame(matched)
    result_df = today_df.copy()
    try:
        existing_df = chart_connector.read_csv(OUTPUT_KEY)
    except Exception as exc:
        logger.warning("Output file not found, creating new one: %s", exc)
        existing_df = pd.DataFrame()

    try:
        if not existing_df.empty and "Scan Time" in existing_df.columns:
            existing_df["Scan Time"] = pd.to_datetime(existing_df["Scan Time"])
            result_df["Scan Time"] = pd.to_datetime(result_df["Scan Time"]) if not result_df.empty else result_df

            today_date = scan_time.date()
            week_start = today_date - timedelta(days=today_date.weekday())
            existing_df = existing_df[existing_df["Scan Time"].dt.date >= week_start]

            combined_df = pd.concat([existing_df, result_df], ignore_index=True)
            combined_df.sort_values("Scan Time", ascending=False, inplace=True)
            combined_df.drop_duplicates(subset=["Security ID"], keep="first", inplace=True)
            result_df = combined_df
    except Exception as exc:
        logger.warning("Weekly merge skipped: %s", exc)

    columns_order = [
        "Stock Name", "Security ID", "Market Cap", "Open", "Price", "High", "Low",
        "EPS Strength", "Price Strength", "Setup_Case", "Scan Time",
    ]
    result_df = result_df.reindex(columns=columns_order)
    chart_connector.write_csv(OUTPUT_KEY, result_df)

    logger.info("EMA momentum file updated | Records=%s | Key=%s", len(result_df), OUTPUT_KEY)

    return today_df


if __name__ == "__main__":
    df = get_ema_breakout_matches()
    print(df)
