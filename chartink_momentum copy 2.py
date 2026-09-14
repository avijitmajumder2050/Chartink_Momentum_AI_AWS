import pandas as pd
import requests
from urllib.parse import unquote


HOME_URL = "https://chartink.com/"
SCAN_URL = "https://chartink.com/screener/process"

CSV_FILE = "chartink_results.csv"


# ============================================================
# CHARTINK SCANNER
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
            # RAW RESULT COUNT
            # =================================================

            rows = data.get("data", [])

            print(
                f"Chartink returned {len(rows)} rows"
            )
            print(
                            f"Chartink returned {rows}"
                        )

            if not rows:

                print("⚠ No stocks found")

                return pd.DataFrame(
                    columns=[
                        "nsecode",
                        "per_chg",
                        "close"
                    ]
                )

            # =================================================
            # BUILD DATAFRAME SAFELY
            # =================================================

            result = []

            for row in rows:

                result.append({
                    "nsecode": str(
                        row.get("nsecode", "")
                    ).strip().upper(),

                    "per_chg": row.get(
                        "per_chg"
                    ),

                    "close": row.get(
                        "close"
                    ),
                })

            df = pd.DataFrame(result)

            # =================================================
            # PRINT FIRST
            # =================================================

            print()
            print("=" * 60)
            print("📢 MATCHING STOCKS")
            print("=" * 60)

            print(
                f"{'SL':<5}"
                f"{'NSE Code':<15}"
                f"{'% Change':>12}"
                f"{'Close':>15}"
            )

            print("-" * 60)

            for i, row in enumerate(
                df.itertuples(index=False),
                start=1
            ):

                nsecode = row.nsecode

                try:
                    per_chg = float(row.per_chg)
                    per_chg_text = f"{per_chg:>11.2f}"
                except:
                    per_chg_text = f"{str(row.per_chg):>11}"

                try:
                    close = float(row.close)
                    close_text = f"{close:>14.2f}"
                except:
                    close_text = f"{str(row.close):>14}"

                print(
                    f"{i:<5}"
                    f"{nsecode:<15}"
                    f"{per_chg_text}"
                    f"{close_text}"
                )

            print("=" * 60)

            # =================================================
            # SAVE AFTER PRINT
            # =================================================

            df.to_csv(
                CSV_FILE,
                index=False
            )

            print(
                f"✅ Results saved: {CSV_FILE}"
            )

            return df

    except requests.HTTPError as e:

        print(
            f"❌ HTTP error: {e}"
        )

        return None

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