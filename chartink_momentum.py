import pandas as pd
import requests
from urllib.parse import unquote

HOME_URL = "https://chartink.com/"
SCAN_URL = "https://chartink.com/screener/process"

CSV_FILE = "chartink_results.csv"


# ============================================================
# CHARTINK SCANNER CONDITION
# ============================================================

condition = {
    "scan_clause": """
    ( {cash} (
        weekly ema( weekly close , 20 ) > weekly ema( weekly close , 50 )
        and weekly ema( weekly close , 50 ) > weekly ema( weekly close , 10 )
        and weekly ema( weekly close , 100 ) > weekly ema( weekly close , 200 )

        and weekly close > weekly ema( weekly close , 20 )
        and weekly close > weekly ema( weekly close , 50 )

        and weekly close >= 0.90 * weekly max( 20 , weekly high )

        and weekly ema( weekly close , 20 )
            > 1 week ago ema( weekly close , 20 )

        and weekly ema( weekly close , 50 )
            > 1 week ago ema( weekly close , 50 )

        and market cap > 2000
    ) )
    """
}


# ============================================================
# GET MOMENTUM STOCKS
# ============================================================

def get_momentum_stocks():

    try:

        # ====================================================
        # SESSION
        # ====================================================

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

            # =================================================
            # OPEN CHARTINK
            # =================================================

            homepage = session.get(
                HOME_URL,
                timeout=30
            )

            print(
                f"Chartink homepage: HTTP "
                f"{homepage.status_code}"
            )

            homepage.raise_for_status()

            # =================================================
            # GET XSRF COOKIE
            # =================================================

            cookies = session.cookies.get_dict()

            print(
                "Cookies:",
                {
                    key: "PRESENT"
                    for key in cookies
                }
            )

            xsrf_token = cookies.get("XSRF-TOKEN")

            if not xsrf_token:

                print()
                print("❌ XSRF-TOKEN cookie not found")

                return None

            xsrf_token = unquote(xsrf_token)

            print("✅ XSRF-TOKEN found")

            # =================================================
            # POST HEADERS
            # =================================================

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

            # =================================================
            # RUN SCANNER
            # =================================================

            response = session.post(
                SCAN_URL,
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

            # =================================================
            # JSON
            # =================================================

            try:
                data = response.json()

            except ValueError:

                print("❌ Chartink did not return JSON")
                print(response.text[:1000])

                return None

            # =================================================
            # RAW RESULT
            # =================================================

            rows = data.get("data", [])

            print(
                f"Chartink returned {len(rows)} rows"
            )

            if not rows:

                print("⚠ No stocks found")

                return pd.DataFrame()

            # =================================================
            # SHOW FIRST RAW ROW
            # =================================================

            print()
            print("=" * 100)
            print("FIRST RAW CHARTINK ROW")
            print("=" * 100)

            print(rows[0])

            print("=" * 100)

            # =================================================
            # SAVE ALL FIELDS
            # =================================================

            df = pd.DataFrame(rows)

            # =================================================
            # NORMALIZE NSE CODE IF PRESENT
            # =================================================

            if "nsecode" in df.columns:

                df["nsecode"] = (
                    df["nsecode"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                )

            # =================================================
            # ADD SERIAL NUMBER
            # =================================================

            df.insert(
                0,
                "SL",
                range(1, len(df) + 1)
            )

            # =================================================
            # PRINT ALL COLUMNS
            # =================================================

            print()
            print("=" * 100)
            print("CHARTINK COLUMNS")
            print("=" * 100)

            for i, column in enumerate(df.columns, start=1):
                print(f"{i:3}. {column}")

            print("=" * 100)

            # =================================================
            # PRINT RESULTS
            # =================================================

            print()
            print("=" * 100)
            print("📢 MATCHING STOCKS")
            print("=" * 100)

            # Print selected important fields if available
            display_columns = [
                column
                for column in [
                    "SL",
                    "nsecode",
                    "name",
                    "close",
                    "per_chg",
                    "market_cap",
                ]
                if column in df.columns
            ]

            if display_columns:
                print(
                    df[display_columns].to_string(
                        index=False
                    )
                )
            else:
                print(df.to_string(index=False))

            print("=" * 100)

            # =================================================
            # SAVE ALL ROW FIELDS
            # =================================================

            df.to_csv(
                CSV_FILE,
                index=False
            )

            print()
            print(
                f"✅ All Chartink fields saved: {CSV_FILE}"
            )

            print(
                f"✅ Rows: {len(df)}"
            )

            print(
                f"✅ Columns: {len(df.columns)}"
            )

            return df

    # ========================================================
    # HTTP ERROR
    # ========================================================

    except requests.HTTPError as e:

        print(
            f"❌ HTTP error: {e}"
        )

        return None

    # ========================================================
    # GENERAL ERROR
    # ========================================================

    except Exception as e:

        print(
            f"❌ Scanner error: {e}"
        )

        return None


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    df = get_momentum_stocks()