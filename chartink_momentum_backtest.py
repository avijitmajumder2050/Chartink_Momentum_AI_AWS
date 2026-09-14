import pandas as pd
import requests
from bs4 import BeautifulSoup as bs
import datetime

# ============================================================
# CHARTINK
# ============================================================

HOME_URL = "https://chartink.com/"
SCREENER_URL = "https://chartink.com/screener/process"
BACKTEST_URL = "https://chartink.com/backtest/process"

BACKTEST_CSV = "chartink_backtest_results.csv"

# Chartink's scan_clause has no token for a specific watchlist (the
# {-1} "default watchlist" token only resolves when the request is
# authenticated, and that login is protected by reCAPTCHA - not
# scriptable). So we scan the full cash segment and filter down to
# the watchlist locally - see WATCHLIST_CSV / load_watchlist_symbols().
WATCHLIST_CSV = "ema_cross_watchlist.csv"


# ============================================================
# WEEKLY MOMENTUM CONDITION
# ============================================================

condition = {
    "scan_clause": """
    ( {cash} (
        weekly ema( weekly close , 20 )
            > weekly ema( weekly close , 50 )

        and weekly ema( weekly close , 50 )
            > weekly ema( weekly close , 10 )

        and weekly ema( weekly close , 100 )
            > weekly ema( weekly close , 200 )

        and weekly close
            > weekly ema( weekly close , 20 )

        and weekly close
            > weekly ema( weekly close , 50 )

        and weekly close
            >= 0.90 * weekly max( 20 , weekly high )

        and weekly ema( weekly close , 20 )
            > 1 week ago ema( weekly close , 20 )

        and weekly ema( weekly close , 50 )
            > 1 week ago ema( weekly close , 50 )

        and market cap > 2000
    ) )
    """
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
            f"backtest will include the full cash segment, unfiltered"
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
                "📊 WEEKLY MOMENTUM BACKTEST"
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
# MAIN
# ============================================================

if __name__ == "__main__":

    df = get_backtest()