import pandas as pd
import requests
from bs4 import BeautifulSoup as bs
from urllib.parse import unquote
import datetime

from connectors import chart_connector, dhan_connector

# Same Chartink-scanning shape as chartink_stoch_backtest.py (that file's
# own comments explain the HTTP/CSRF dance in full) — this is a second,
# independent scan with its own condition and its own CSV files, not a
# shared abstraction, matching how dhan_ema_breakout.py and
# chartink_stoch_backtest.py are already separate, self-contained scanner
# scripts rather than plugins into one shared engine.

LIVE_SCAN_CSV = "chartink_hammer_live_scan.csv"
BACKTEST_CSV = "chartink_hammer_backtest_results.csv"
COMBINED_CSV = "chartink_hammer_combined_last7.csv"

# Chartink's scan_clause has no token for a specific watchlist, so we scan
# the full cash segment and filter down to the watchlist locally — same
# file the stochastic-crossover scan already filters against, so both
# scanners agree on "the tracked universe".
WATCHLIST_CSV = "ema_cross_watchlist.csv"

HOME_URL = "https://chartink.com/"
SCREENER_URL = "https://chartink.com/screener/process"
BACKTEST_URL = "https://chartink.com/backtest/process"


# ============================================================
# DAILY HAMMER CONDITION
#
# The whole clause is wrapped in {-1} (Chartink's "as of 1 trading day
# ago" shift) — this scans for a hammer + EMA-cross + bullish-alignment
# setup that completed YESTERDAY, so today's session can be used to
# confirm/act on it (e.g. entry on a break of yesterday's hammer high),
# not a same-day intraday scan.
#
#   1. Hammer candle shape (on the {-1} day):
#      - lower shadow (least(close,open) - low) > 50% of the day's range
#      - body (abs(open-close)) < 30% of the day's range
#   2. EMA cross (on the {-1} day, vs the day before that): close crossed
#      above EMA20 OR crossed above EMA50
#   3. Bullish EMA alignment (on the {-1} day): EMA10 >= EMA20 >= EMA50
#      >= EMA200
# ============================================================

condition = {
    "scan_clause": (
        "( {-1} ( ( {cash} (  (  daily high -  daily low ) *  0.50 <  least(   daily close,  daily open  ) -  daily low and  abs(  daily open -  daily close ) <  (  daily high -  daily low ) *  0.30 ) ) and( {cash} (  daily close >  daily ema(  daily close , 20 ) and  1 day ago  close <=  1 day ago  ema(  daily close , 20 ) or  daily close >  daily ema(  daily close , 50 ) and  1 day ago  close <=  1 day ago  ema(  daily close , 50 ) ) ) and( {cash} (  daily ema(  daily close , 10 ) >=  daily ema(  daily close , 20 ) and  daily ema(  daily close , 20 ) >=  daily ema(  daily close , 50 ) and  daily ema(  daily close , 50 ) >=  daily ema(  daily close , 200 ) ) ) ) )"
    ),
    "debug_clause": (
        "groupcount( 1 where  ( daily high -  daily low ) *  0.50 <  least( daily close,  daily open ) -  daily low),"
        "groupcount( 1 where  abs( daily open -  daily close ) <  ( daily high -  daily low ) *  0.30),"
        "groupcount( 1 where  daily close >  daily ema( daily close , 20 ) and  1 day ago close <=  1 day ago  ema( daily close , 20 )),"
        "groupcount( 1 where  daily close >  daily ema( daily close , 50 ) and  1 day ago close <=  1 day ago  ema( daily close , 50 )),"
        "groupcount( 1 where  daily ema( daily close , 10 ) >=  daily ema( daily close , 20 ) and  daily ema( daily close , 20 ) >=  daily ema( daily close , 50 ) and  daily ema( daily close , 50 ) >=  daily ema( daily close , 200 ))"
    ),
    "column_clause": (
        " Daily Close as 'scan-column-default-close',  Daily "
        "\"close - 1 candle ago close / 1 candle ago close * 100\" "
        "as 'scan-column-default-percent-change', filternumber( daily close >  "
        "1 day ago close,1) as 'default-percent-change-conditional-filters-color',  "
        "Daily Volume as 'scan-column-default-volume', "
        "Daily High as 'scan-column-high', Daily Low as 'scan-column-low'"
    ),
}


# ============================================================
# WATCHLIST FILTER
# ============================================================

def load_watchlist_symbols(path):
    try:
        wl_df = pd.read_csv(path)
    except FileNotFoundError:
        print(f"⚠ Watchlist file not found: {path} - results will include the full cash segment, unfiltered")
        return None

    column = None
    for candidate in ("Symbol", "Stock", "symbol", "stock"):
        if candidate in wl_df.columns:
            column = candidate
            break

    if column is None:
        print(f"❌ Watchlist file {path} has no Symbol/Stock column")
        return None

    symbols = set(wl_df[column].astype(str).str.strip().str.upper())
    print(f"✅ Loaded {len(symbols)} symbols from watchlist: {path}")
    return symbols


# ============================================================
# DHAN FALLBACK FOR HIGH/LOW/PRICE
# ============================================================

def _last_daily_bar_from_dhan(security_id):
    """Most recent daily candle for one security_id — see chartink_stoch_
    backtest.py's identical helper for the full rationale (outside-market-
    hours fallback when Dhan's own live quote has nothing either)."""
    to_date = datetime.date.today().strftime("%Y-%m-%d")
    from_date = (datetime.date.today() - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    bars = dhan_connector.get_historical_daily(security_id, from_date, to_date)
    if bars is None or bars.empty:
        return None
    last = bars.iloc[-1]
    return {"high": float(last["high"]), "low": float(last["low"]), "close": float(last["close"])}


def _fill_missing_prices_from_dhan(df, symbol_col="nsecode"):
    """Fills gaps in High/Low/Price — see chartink_stoch_backtest.py's
    identical helper for the full rationale (Chartink's own price columns
    coming back blank, or a backtest-only match never having one at all)."""
    for column in ("High", "Low", "Price"):
        if column not in df.columns:
            df[column] = pd.NA

    missing = df[df["High"].isna() | df["Low"].isna() | df["Price"].isna()]
    if missing.empty or symbol_col not in df.columns:
        return df

    try:
        symbols = missing[symbol_col].astype(str).str.upper().tolist()
        resolved, unresolved = dhan_connector.resolve_security_ids(symbols)
        if unresolved:
            print(f"⚠ Dhan fallback: couldn't resolve security IDs for {unresolved}")
        if not resolved:
            return df

        live_ohlc = chart_connector.get_live_ohlc(list(resolved.values()))

        filled_live = 0
        filled_eod = 0
        for idx, row in missing.iterrows():
            symbol = str(row[symbol_col]).upper()
            security_id = resolved.get(symbol)
            if not security_id:
                continue

            bar = live_ohlc.get(str(security_id))
            if bar:
                filled_live += 1
            else:
                bar = _last_daily_bar_from_dhan(security_id)
                if bar:
                    filled_eod += 1

            if not bar:
                continue
            if pd.isna(df.at[idx, "High"]):
                df.at[idx, "High"] = bar["high"]
            if pd.isna(df.at[idx, "Low"]):
                df.at[idx, "Low"] = bar["low"]
            if pd.isna(df.at[idx, "Price"]):
                df.at[idx, "Price"] = bar["close"]

        if filled_live or filled_eod:
            print(f"✅ Dhan fallback filled High/Low/Price for {filled_live} stock(s) from live quotes, {filled_eod} from the last daily candle")

    except Exception as exc:
        print(f"⚠ Dhan High/Low/Price fallback failed, leaving gaps as-is: {exc}")

    return df


# ============================================================
# LIVE SCANNER (TODAY'S MATCHES)
# ============================================================

def get_live_scan():
    try:
        with requests.Session() as session:
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            )
            session.headers.update({"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"})

            homepage = session.get(HOME_URL, timeout=30)
            print(f"Chartink homepage: HTTP {homepage.status_code}")
            homepage.raise_for_status()

            cookies = session.cookies.get_dict()
            xsrf_token = cookies.get("XSRF-TOKEN")
            if not xsrf_token:
                print("❌ XSRF-TOKEN cookie not found")
                return None
            xsrf_token = unquote(xsrf_token)
            print("✅ XSRF-TOKEN found")

            headers = {
                "User-Agent": user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": xsrf_token,
                "Referer": HOME_URL,
                "Origin": "https://chartink.com",
            }

            print()
            print("=" * 100)
            print("STARTING CHARTINK LIVE SCAN — DAILY HAMMER")
            print("=" * 100)

            response = session.post(SCREENER_URL, data=condition, headers=headers, timeout=60)
            print(f"Scanner response: HTTP {response.status_code}")

            if response.status_code == 419:
                print("❌ Chartink CSRF error (419)")
                print(response.text[:500])
                return None

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                print("❌ Chartink did not return JSON")
                print(response.text[:1000])
                return None

            rows = data.get("data", [])
            print(f"Chartink returned {len(rows)} rows")

            if not rows:
                print("⚠ No live matches today")
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df = df.rename(columns={
                "scan-column-high": "High",
                "scan-column-low": "Low",
                "scan-column-default-close": "Price",
            })

            if "nsecode" in df.columns:
                df["nsecode"] = df["nsecode"].astype(str).str.strip().str.upper()

            today = datetime.date.today().strftime("%Y-%m-%d")
            df.insert(0, "Date", today)

            watchlist_symbols = load_watchlist_symbols(WATCHLIST_CSV)
            if watchlist_symbols is not None and "nsecode" in df.columns:
                df = df[df["nsecode"].isin(watchlist_symbols)].reset_index(drop=True)

            print()
            print("=" * 100)
            print("📢 LIVE SCAN MATCHES")
            print("=" * 100)

            if df.empty:
                print("⚠ No live matches in watchlist today")
                return pd.DataFrame()

            display_columns = [c for c in ["Date", "nsecode", "name", "close", "per_chg"] if c in df.columns]
            print(df[display_columns].to_string(index=False) if display_columns else df.to_string(index=False))
            print("=" * 100)

            df.to_csv(LIVE_SCAN_CSV, index=False)
            print()
            print(f"✅ Live scan saved to: {LIVE_SCAN_CSV}")

            return df

    except requests.HTTPError as e:
        print(f"❌ HTTP error: {e}")
        return None
    except Exception as e:
        print(f"❌ Live scan error: {e}")
        return None


# ============================================================
# BACKTEST
# ============================================================

def get_backtest():
    try:
        with requests.Session() as s:
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            )
            s.headers.update({"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"})

            r_data = s.get(SCREENER_URL, timeout=30)
            print(f"Chartink screener: HTTP {r_data.status_code}")
            r_data.raise_for_status()

            soup = bs(r_data.content, "lxml")
            meta = soup.find("meta", {"name": "csrf-token"})
            if meta is None:
                print("❌ CSRF meta tag not found")
                print(r_data.text[:1000])
                return None

            csrf_token = meta.get("content")
            if not csrf_token:
                print("❌ CSRF token is empty")
                return None
            print("✅ CSRF token found")

            headers = {
                "User-Agent": user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "x-csrf-token": csrf_token,
                "Referer": SCREENER_URL,
                "Origin": "https://chartink.com",
            }

            print()
            print("=" * 100)
            print("STARTING CHARTINK BACKTEST — DAILY HAMMER")
            print("=" * 100)

            response = s.post(BACKTEST_URL, headers=headers, data=condition, timeout=120)
            print(f"Backtest response: HTTP {response.status_code}")

            if response.status_code == 419:
                print("❌ Chartink CSRF error 419")
                print(response.text[:1000])
                return None

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                print("❌ Chartink response is not JSON")
                print(response.text[:2000])
                return None

            meta_data = data.get("metaData", [])
            aggregated_stock_list = data.get("aggregatedStockList", [])
            print(f"Historical dates : {len(meta_data)}")
            print(f"Stock-list rows  : {len(aggregated_stock_list)}")

            if not meta_data:
                print("⚠ No metaData returned")
                return pd.DataFrame()

            final_data = []
            trade_times = meta_data[0].get("tradeTimes", [])
            print(f"Trade dates returned: {len(trade_times)}")

            for i in range(len(trade_times)):
                stocks = []
                if i < len(aggregated_stock_list) and aggregated_stock_list[i] != []:
                    stock = aggregated_stock_list[i]
                    for j in range(len(stock)):
                        if j % 3 == 0:
                            stocks.append(stock[j])

                trade_date = datetime.datetime.fromtimestamp(trade_times[i] / 1000)
                final_data.append({
                    "Date": trade_date.strftime("%Y-%m-%d"),
                    "Stock": stocks,
                    "Stock_Count": len(stocks),
                })

            df = pd.DataFrame(final_data)

            print()
            print("=" * 120)
            print("🔨 DAILY HAMMER BACKTEST")
            print("=" * 120)
            for _, row in df.iterrows():
                print()
                print(f"Date       : {row['Date']}")
                print(f"Stock Count: {row['Stock_Count']}")
                print(f"Stocks     : {row['Stock']}")
            print()
            print("=" * 120)

            expanded_rows = []
            for _, row in df.iterrows():
                for stock in row["Stock"]:
                    expanded_rows.append({
                        "Date": row["Date"],
                        "Stock": str(stock).strip().upper(),
                        "Stock_Count": row["Stock_Count"],
                    })

            expanded_df = pd.DataFrame(expanded_rows)

            watchlist_symbols = load_watchlist_symbols(WATCHLIST_CSV)
            if watchlist_symbols is not None and not expanded_df.empty:
                expanded_df = expanded_df[expanded_df["Stock"].isin(watchlist_symbols)].reset_index(drop=True)

            print()
            print("=" * 120)
            print("📈 STOCK-BY-STOCK BACKTEST")
            print("=" * 120)
            if expanded_df.empty:
                print("⚠ No historical stock matches")
            else:
                print(expanded_df.to_string(index=False))
            print("=" * 120)

            expanded_df.to_csv(BACKTEST_CSV, index=False)
            print()
            print(f"✅ Backtest saved to: {BACKTEST_CSV}")
            print(f"✅ Historical dates: {len(df)}")
            print(f"✅ Historical stock signals: {len(expanded_df)}")

            return expanded_df

    except requests.HTTPError as e:
        print(f"❌ HTTP error: {e}")
        return None
    except Exception as e:
        print(f"❌ Backtest error: {e}")
        return None


# ============================================================
# COMBINE LIVE SCAN + LAST N TRADING DAYS
# ============================================================

def get_last_n_trading_days(n, end_date=None):
    # Approximates NSE trading days as Mon-Fri business days. Does not
    # account for exchange holidays (no holiday calendar is tracked in
    # this project) — same approximation chartink_stoch_backtest.py uses.
    end_date = end_date or datetime.date.today()
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end=end_date, periods=n)]


def combine_live_and_backtest(live_df, backtest_df, days=7):
    recent_dates = get_last_n_trading_days(days)

    if backtest_df is None or backtest_df.empty:
        recent_df = pd.DataFrame(columns=["Date", "Stock"])
    else:
        recent_df = backtest_df[backtest_df["Date"].isin(recent_dates)]

    backtest_stocks = (
        recent_df.groupby("Stock")["Date"].apply(lambda dates: ", ".join(sorted(set(dates)))).to_dict()
    )

    if live_df is None or live_df.empty:
        live_stocks = set()
        live_prices = {}
    else:
        live_df = live_df.copy()
        live_df["nsecode"] = live_df["nsecode"].astype(str).str.upper()
        live_stocks = set(live_df["nsecode"])
        price_cols = [c for c in ("High", "Low", "Price") if c in live_df.columns]
        live_prices = live_df.set_index("nsecode")[price_cols].to_dict("index") if price_cols else {}

    all_stocks = sorted(set(backtest_stocks.keys()) | live_stocks)

    rows = []
    for stock in all_stocks:
        price = live_prices.get(stock, {})
        rows.append({
            "Stock": stock,
            "In_Live_Scan_Today": stock in live_stocks,
            "Backtest_Dates_Last_{}".format(days): backtest_stocks.get(stock, ""),
            "Price": price.get("Price"),
            "High": price.get("High"),
            "Low": price.get("Low"),
        })

    combined_df = pd.DataFrame(rows)

    if not combined_df.empty:
        combined_df = _fill_missing_prices_from_dhan(combined_df, symbol_col="Stock")

    print()
    print("=" * 120)
    print(f"🔗 COMBINED: LIVE SCAN + LAST {days} BACKTEST DATES ({', '.join(recent_dates) if recent_dates else 'none'})")
    print("=" * 120)

    if combined_df.empty:
        print("⚠ No stocks in live scan or recent backtest")
    else:
        print(combined_df.to_string(index=False))

    print("=" * 120)

    combined_df.to_csv(COMBINED_CSV, index=False)
    print()
    print(f"✅ Combined list saved to: {COMBINED_CSV}")

    return combined_df


if __name__ == "__main__":
    backtest_df = get_backtest()
    live_df = get_live_scan()
    combined = combine_live_and_backtest(live_df, backtest_df, days=7)
