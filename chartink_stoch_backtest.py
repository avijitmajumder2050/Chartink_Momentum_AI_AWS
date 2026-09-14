import pandas as pd
import requests
from bs4 import BeautifulSoup as bs
from urllib.parse import unquote
import datetime

from connectors import chart_connector, dhan_connector

LIVE_SCAN_CSV = "chartink_stoch_live_scan.csv"
COMBINED_CSV = "chartink_stoch_combined_last10.csv"

# Chartink's scan_clause has no token for a specific watchlist, so we scan
# the full cash segment and filter down to the watchlist locally.
WATCHLIST_CSV = "ema_cross_watchlist.csv"


# ============================================================
# CHARTINK
# ============================================================

HOME_URL = "https://chartink.com/"
SCREENER_URL = "https://chartink.com/screener/process"
BACKTEST_URL = "https://chartink.com/backtest/process"

BACKTEST_CSV = "chartink_stoch_backtest_results.csv"


# ============================================================
# STOCHASTIC CROSSOVER CONDITION
# ============================================================

condition = {
    "scan_clause": (
        "( {cash} (  daily slow stochastic %d( 4,3 ) >  20 and  1 day ago  "
        "slow stochastic %d( 4,3 ) <=  20 and  daily slow stochastic %k( 4 , 3 ) "
        ">  20 and  1 day ago  slow stochastic %k( 4 , 3 ) <=  20 and  daily rsi( 14 ) "
        "<  50 and  daily close <  daily ema(  daily close , 50 ) ) )"
    ),
    "debug_clause": (
        "groupcount( 1 where  daily slow stochastic %d( 4,3 ) >  20 and  1 day ago  "
        "slow stochastic %d( 4,3 ) <=  20),groupcount( 1 where  daily slow stochastic "
        "%k( 4 , 3 ) >  20 and  1 day ago  slow stochastic %k( 4 , 3 ) <=  20),"
        "groupcount( 1 where  daily rsi( 14 ) <  50),groupcount( 1 where  daily close "
        "<  daily ema(  daily close , 50 ))"
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

        print(
            f"⚠ Watchlist file not found: {path} - "
            f"results will include the full cash segment, unfiltered"
        )

        return None

    column = None

    for candidate in ("Symbol", "Stock", "symbol", "stock"):

        if candidate in wl_df.columns:

            column = candidate

            break

    if column is None:

        print(
            f"❌ Watchlist file {path} has no Symbol/Stock column"
        )

        return None

    symbols = set(
        wl_df[column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    print(
        f"✅ Loaded {len(symbols)} symbols from watchlist: {path}"
    )

    return symbols


# ============================================================
# DHAN FALLBACK FOR HIGH/LOW/PRICE
# ============================================================

def _last_daily_bar_from_dhan(security_id):
    """Most recent daily candle (yesterday's close, typically) for one
    security_id — the fallback-of-fallback for outside market hours, when
    Dhan's own live quote_data() has nothing to offer either (it only
    serves data while the market's actually open). A 10 calendar-day
    window comfortably covers the most recent trading day across any
    weekend/holiday gap; returns None if nothing comes back."""
    to_date = datetime.date.today().strftime("%Y-%m-%d")
    from_date = (datetime.date.today() - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    bars = dhan_connector.get_historical_daily(security_id, from_date, to_date)
    if bars is None or bars.empty:
        return None
    last = bars.iloc[-1]
    return {"high": float(last["high"]), "low": float(last["low"]), "close": float(last["close"])}


def _fill_missing_prices_from_dhan(df, symbol_col="nsecode"):
    """Fills gaps in High/Low/Price for the stock's symbol — used for two
    different gaps: (1) Chartink's own scan-columns coming back blank for a
    stock it DID match live today, and (2) a stock that only matched via
    backtest history (not today's live scan), which never had a Chartink
    price to begin with. Either way, Dhan can't replace Chartink's actual
    scan/filter step (only Chartink knows which stocks match the
    stochastic-crossover condition), so this only ever fills price data for
    symbols Chartink already told us matched, on some day.

    Two Dhan tiers, tried in order per symbol: live quote first (today's
    actual high/low while the market's open), then the most recent daily
    candle (e.g. yesterday's close) if the live quote has nothing — which
    is what actually happens outside market hours, since quote_data() only
    serves data while NSE is open. Best-effort throughout, never raises."""

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
            print(
                f"✅ Dhan fallback filled High/Low/Price for {filled_live} stock(s) "
                f"from live quotes, {filled_eod} from the last daily candle"
            )

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
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            )

            session.headers.update({
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            })

            # ------------------------------------------------
            # OPEN CHARTINK HOMEPAGE
            # ------------------------------------------------

            homepage = session.get(
                HOME_URL,
                timeout=30
            )

            print(
                f"Chartink homepage: HTTP "
                f"{homepage.status_code}"
            )

            homepage.raise_for_status()

            # ------------------------------------------------
            # XSRF COOKIE
            # ------------------------------------------------

            cookies = session.cookies.get_dict()

            xsrf_token = cookies.get("XSRF-TOKEN")

            if not xsrf_token:

                print("❌ XSRF-TOKEN cookie not found")

                return None

            xsrf_token = unquote(xsrf_token)

            print("✅ XSRF-TOKEN found")

            # ------------------------------------------------
            # POST HEADERS
            # ------------------------------------------------

            headers = {
                "User-Agent": user_agent,
                "Accept": (
                    "application/json, text/javascript, "
                    "*/*; q=0.01"
                ),
                "Content-Type": (
                    "application/x-www-form-urlencoded; "
                    "charset=UTF-8"
                ),
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": xsrf_token,
                "Referer": HOME_URL,
                "Origin": "https://chartink.com",
            }

            # ------------------------------------------------
            # RUN SCANNER
            # ------------------------------------------------

            print()
            print("=" * 100)
            print("STARTING CHARTINK LIVE SCAN")
            print("=" * 100)

            response = session.post(
                SCREENER_URL,
                data=condition,
                headers=headers,
                timeout=60
            )

            print(
                f"Scanner response: HTTP "
                f"{response.status_code}"
            )

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

            print(
                f"Chartink returned {len(rows)} rows"
            )

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

                df["nsecode"] = (
                    df["nsecode"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                )

            today = datetime.date.today().strftime(
                "%Y-%m-%d"
            )

            df.insert(0, "Date", today)

            watchlist_symbols = load_watchlist_symbols(
                WATCHLIST_CSV
            )

            if (
                watchlist_symbols is not None
                and "nsecode" in df.columns
            ):

                df = df[
                    df["nsecode"].isin(watchlist_symbols)
                ].reset_index(drop=True)

            print()
            print("=" * 100)
            print("📢 LIVE SCAN MATCHES")
            print("=" * 100)

            if df.empty:

                print("⚠ No live matches in watchlist today")

                return pd.DataFrame()

            # Dhan fallback runs once, later, on the final combined result
            # (combine_live_and_backtest) — that covers backtest-only
            # matches too, not just today's live rows, so it isn't needed
            # here as well.

            display_columns = [
                column
                for column in [
                    "Date",
                    "nsecode",
                    "name",
                    "close",
                    "per_chg",
                ]
                if column in df.columns
            ]

            print(
                df[display_columns].to_string(index=False)
                if display_columns
                else df.to_string(index=False)
            )

            print("=" * 100)

            df.to_csv(
                LIVE_SCAN_CSV,
                index=False
            )

            print()
            print(
                f"✅ Live scan saved to: {LIVE_SCAN_CSV}"
            )

            return df

    except requests.HTTPError as e:

        print(
            f"❌ HTTP error: {e}"
        )

        return None

    except Exception as e:

        print(
            f"❌ Live scan error: {e}"
        )

        return None


# ============================================================
# BACKTEST
# ============================================================

def get_backtest():

    try:

        with requests.Session() as s:

            # ------------------------------------------------
            # HEADERS
            # ------------------------------------------------

            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            )

            s.headers.update({
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            })

            # ------------------------------------------------
            # OPEN SCREENER PAGE
            # ------------------------------------------------

            r_data = s.get(
                SCREENER_URL,
                timeout=30
            )

            print(
                f"Chartink screener: HTTP "
                f"{r_data.status_code}"
            )

            r_data.raise_for_status()

            # ------------------------------------------------
            # GET CSRF TOKEN
            # ------------------------------------------------

            soup = bs(
                r_data.content,
                "lxml"
            )

            meta = soup.find(
                "meta",
                {
                    "name": "csrf-token"
                }
            )

            if meta is None:

                print(
                    "❌ CSRF meta tag not found"
                )

                print(
                    r_data.text[:1000]
                )

                return None

            csrf_token = meta.get("content")

            if not csrf_token:

                print(
                    "❌ CSRF token is empty"
                )

                return None

            print(
                "✅ CSRF token found"
            )

            # ------------------------------------------------
            # XSRF COOKIE
            # ------------------------------------------------

            cookies = s.cookies.get_dict()

            print(
                "Cookies:",
                {
                    key: "PRESENT"
                    for key in cookies
                }
            )

            # ------------------------------------------------
            # REQUEST HEADERS
            # ------------------------------------------------

            headers = {
                "User-Agent": user_agent,
                "Accept": (
                    "application/json, text/javascript, "
                    "*/*; q=0.01"
                ),
                "Content-Type": (
                    "application/x-www-form-urlencoded; "
                    "charset=UTF-8"
                ),
                "X-Requested-With": "XMLHttpRequest",
                "x-csrf-token": csrf_token,
                "Referer": SCREENER_URL,
                "Origin": "https://chartink.com",
            }

            # ------------------------------------------------
            # BACKTEST REQUEST
            # ------------------------------------------------

            print()
            print("=" * 100)
            print("STARTING CHARTINK BACKTEST")
            print("=" * 100)

            response = s.post(
                BACKTEST_URL,
                headers=headers,
                data=condition,
                timeout=120
            )

            print(
                f"Backtest response: HTTP "
                f"{response.status_code}"
            )

            if response.status_code == 419:

                print(
                    "❌ Chartink CSRF error 419"
                )

                print(
                    response.text[:1000]
                )

                return None

            response.raise_for_status()

            # ------------------------------------------------
            # JSON RESPONSE
            # ------------------------------------------------

            try:

                data = response.json()

            except ValueError:

                print(
                    "❌ Chartink response is not JSON"
                )

                print(
                    response.text[:2000]
                )

                return None

            # ------------------------------------------------
            # SHOW RESPONSE STRUCTURE
            # ------------------------------------------------

            print()
            print("=" * 100)
            print("BACKTEST RESPONSE KEYS")
            print("=" * 100)

            print(
                data.keys()
            )

            # ------------------------------------------------
            # GET METADATA
            # ------------------------------------------------

            meta_data = data.get(
                "metaData",
                []
            )

            aggregated_stock_list = data.get(
                "aggregatedStockList",
                []
            )

            print()
            print(
                f"Historical dates : "
                f"{len(meta_data)}"
            )

            print(
                f"Stock-list rows  : "
                f"{len(aggregated_stock_list)}"
            )

            if not meta_data:

                print(
                    "⚠ No metaData returned"
                )

                return pd.DataFrame()

            # =================================================
            # PARSE BACKTEST
            # =================================================

            final_data = []

            trade_times = meta_data[0].get(
                "tradeTimes",
                []
            )

            print()
            print(
                f"Trade dates returned: "
                f"{len(trade_times)}"
            )

            # ------------------------------------------------
            # SAME LOGIC AS YOUR WORKING SCRIPT
            # ------------------------------------------------

            for i in range(
                len(trade_times)
            ):

                stocks = []

                if (
                    i <
                    len(aggregated_stock_list)
                    and aggregated_stock_list[i] != []
                ):

                    stock = aggregated_stock_list[i]

                    for j in range(
                        len(stock)
                    ):

                        if j % 3 == 0:

                            stocks.append(
                                stock[j]
                            )

                # ------------------------------------------------
                # DATE
                # ------------------------------------------------

                trade_date = (
                    datetime.datetime.fromtimestamp(
                        trade_times[i] / 1000
                    )
                )

                # ------------------------------------------------
                # RESULT
                # ------------------------------------------------

                final_data.append({

                    "Date":
                        trade_date.strftime(
                            "%Y-%m-%d"
                        ),

                    "Stock":
                        stocks,

                    "Stock_Count":
                        len(stocks)
                })

            # =================================================
            # DATAFRAME
            # =================================================

            df = pd.DataFrame(
                final_data
            )

            # =================================================
            # PRINT BACKTEST
            # =================================================

            print()
            print("=" * 120)
            print(
                "📊 STOCHASTIC CROSSOVER BACKTEST"
            )
            print("=" * 120)

            for _, row in df.iterrows():

                print()
                print(
                    f"Date       : "
                    f"{row['Date']}"
                )

                print(
                    f"Stock Count: "
                    f"{row['Stock_Count']}"
                )

                print(
                    f"Stocks     : "
                    f"{row['Stock']}"
                )

            print()
            print("=" * 120)

            # =================================================
            # EXPLODE STOCKS
            # =================================================
            #
            # This creates one row per stock/date.
            #
            # Example:
            #
            # 2026-07-03 | AETHER
            # 2026-07-03 | M&MFIN
            # 2026-07-03 | LALPATHLAB
            #
            # =================================================

            expanded_rows = []

            for _, row in df.iterrows():

                for stock in row["Stock"]:

                    expanded_rows.append({

                        "Date":
                            row["Date"],

                        "Stock":
                            str(stock)
                            .strip()
                            .upper(),

                        "Stock_Count":
                            row["Stock_Count"]
                    })

            expanded_df = pd.DataFrame(
                expanded_rows
            )

            # =================================================
            # FILTER TO WATCHLIST
            # =================================================

            watchlist_symbols = load_watchlist_symbols(
                WATCHLIST_CSV
            )

            if (
                watchlist_symbols is not None
                and not expanded_df.empty
            ):

                expanded_df = expanded_df[
                    expanded_df["Stock"].isin(watchlist_symbols)
                ].reset_index(drop=True)

            # =================================================
            # PRINT EXPANDED RESULT
            # =================================================

            print()
            print("=" * 120)
            print(
                "📈 STOCK-BY-STOCK BACKTEST"
            )
            print("=" * 120)

            if expanded_df.empty:

                print(
                    "⚠ No historical stock matches"
                )

            else:

                print(
                    expanded_df.to_string(
                        index=False
                    )
                )

            print("=" * 120)

            # =================================================
            # SAVE
            # =================================================

            expanded_df.to_csv(
                BACKTEST_CSV,
                index=False
            )

            print()
            print(
                f"✅ Backtest saved to: "
                f"{BACKTEST_CSV}"
            )

            print(
                f"✅ Historical dates: "
                f"{len(df)}"
            )

            print(
                f"✅ Historical stock signals: "
                f"{len(expanded_df)}"
            )

            return expanded_df

    except requests.HTTPError as e:

        print(
            f"❌ HTTP error: {e}"
        )

        return None

    except Exception as e:

        print(
            f"❌ Backtest error: {e}"
        )

        return None


# ============================================================
# COMBINE LIVE SCAN + LAST N TRADING DAYS
# ============================================================

def get_last_n_trading_days(n, end_date=None):

    # Approximates NSE trading days as Mon-Fri business days.
    # Does not account for exchange holidays (no holiday
    # calendar is tracked in this project).

    end_date = end_date or datetime.date.today()

    return [
        d.strftime("%Y-%m-%d")
        for d in pd.bdate_range(end=end_date, periods=n)
    ]


def combine_live_and_backtest(live_df, backtest_df, days=5):

    recent_dates = get_last_n_trading_days(days)

    if backtest_df is None or backtest_df.empty:

        recent_df = pd.DataFrame(columns=["Date", "Stock"])

    else:

        recent_df = backtest_df[
            backtest_df["Date"].isin(recent_dates)
        ]

    backtest_stocks = (
        recent_df
        .groupby("Stock")["Date"]
        .apply(lambda dates: ", ".join(sorted(set(dates))))
        .to_dict()
    )

    if live_df is None or live_df.empty:
        live_stocks = set()
        live_prices = {}
    else:
        live_df = live_df.copy()
        live_df["nsecode"] = live_df["nsecode"].astype(str).str.upper()
        live_stocks = set(live_df["nsecode"])
        # Only today's live matches carry a High/Low/Price (Chartink's live
        # scan, not the backtest) — a stock present only via backtest
        # history has no today's price data to offer, so it's left blank.
        price_cols = [c for c in ("High", "Low", "Price") if c in live_df.columns]
        live_prices = live_df.set_index("nsecode")[price_cols].to_dict("index") if price_cols else {}

    all_stocks = sorted(
        set(backtest_stocks.keys()) | live_stocks
    )

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
        # Runs on the FULL combined result, not just today's live matches —
        # a backtest-only stock (matched on some day in the last N, but not
        # today) never had a Chartink price at all, so it needs today's
        # current price from Dhan just as much as a live match with a gap.
        combined_df = _fill_missing_prices_from_dhan(combined_df, symbol_col="Stock")

    print()
    print("=" * 120)
    print(
        f"🔗 COMBINED: LIVE SCAN + LAST {days} BACKTEST DATES "
        f"({', '.join(recent_dates) if recent_dates else 'none'})"
    )
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


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    backtest_df = get_backtest()

    live_df = get_live_scan()

    combined = combine_live_and_backtest(
        live_df,
        backtest_df,
        days=10
    )
