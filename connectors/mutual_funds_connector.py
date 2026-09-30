"""Mutual Funds page data — kept as JSON in S3 at uploads/mutual_funds.json
(upload_mutual_funds.py uploads a hand-edited copy; the copy bundled in the
repo is the fallback if S3 is unreachable).

Refreshed automatically once a day (refresh_daily(), started by app.py
when the backend starts) from official / free sources — no scraping of
Groww or INDmoney:

  * NAV — AMFI's daily NAV file (portal.amfiindia.com NAVAll.txt), which
    lists every scheme with its latest NAV. AMFI publishes each day's
    NAVs overnight, so the 09:00 backend start always has the previous
    trading day.
  * 1Y / 3Y / 5Y returns — calculated here from each fund's full NAV
    history (api.mfapi.in, built on AMFI data): 1Y point-to-point, 3Y
    and 5Y annualised (CAGR). One consistent method for every fund.
  * ETF last price and 1M / 1Y change — Dhan daily candles (NSE close).

Not refreshed (they change monthly or rarely, and have no free official
daily feed): AUM, expense ratio, exit load, minimums, lock-in. Those stay
as last uploaded; aumDate on each fund says when.

Each fund is matched by its AMFI scheme code (amfiCode: Direct Plan,
Growth for funds). A fund whose refresh fails keeps its previous numbers,
and nothing is written unless most of the refresh succeeded.
"""

import datetime
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from connectors import cache, chart_connector

S3_KEY = "uploads/mutual_funds.json"
LOCAL_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mutual_funds.json")
CACHE_KEY = "mutual_funds_snapshot"
CACHE_TTL_SECONDS = 60 * 60

AMFI_NAV_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
MFAPI_URL = "https://api.mfapi.in/mf/{code}"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
HTTP_TIMEOUT_SECONDS = 30
HISTORY_WORKERS = 4
# Write back only if at least this share of funds refreshed — a source
# outage shouldn't overwrite good figures with a half-empty set.
MIN_SUCCESS_SHARE = 0.6
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _load():
    try:
        client = chart_connector._s3()
        bucket = chart_connector._get_bucket(client)
        data = json.loads(client.get_object(Bucket=bucket, Key=S3_KEY)["Body"].read())
        source = "s3"
    except Exception:
        with open(LOCAL_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
        source = "bundled"
    data["source"] = source
    return data


def get_mutual_funds():
    return cache.get_or_fetch(CACHE_KEY, CACHE_TTL_SECONDS, _load)


# ---------------------------------------------------------------------
# Daily refresh
# ---------------------------------------------------------------------
def _amfi_navs():
    """{scheme code: (nav, date)} from AMFI's daily file.
    Format: code;ISIN growth;ISIN reinvest;name;plan;option;NAV;date"""
    resp = requests.get(AMFI_NAV_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    out = {}
    for line in resp.text.splitlines():
        p = line.split(";")
        if len(p) < 8 or not p[0].strip().isdigit():
            continue
        try:
            out[p[0].strip()] = (float(p[-2]), datetime.datetime.strptime(p[-1].strip(), "%d-%b-%Y").date())
        except ValueError:
            continue
    if len(out) < 1000:
        raise RuntimeError(f"AMFI NAV file looks incomplete ({len(out)} schemes)")
    return out


def _nav_history(code):
    """[(date, nav)] oldest first."""
    resp = requests.get(MFAPI_URL.format(code=code), headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    rows = []
    for r in resp.json().get("data", []):
        try:
            rows.append((datetime.datetime.strptime(r["date"], "%d-%m-%Y").date(), float(r["nav"])))
        except (KeyError, ValueError):
            continue
    rows.sort()
    return rows


def _years_before(d, years):
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year - years, day=28)


def _value_on_or_before(series, target):
    """Last value dated on or before target; None if the series starts later."""
    best = None
    for d, v in series:
        if d > target:
            break
        best = v
    return best


def returns_from_history(series):
    """(return1y %, cagr3y %, cagr5y %) from [(date, nav)] — 1Y point to
    point, 3Y/5Y annualised. None where history is too short."""
    if not series:
        return None, None, None
    end_date, end_nav = series[-1]
    if series[0][0] > _years_before(end_date, 1):
        return None, None, None
    out = []
    for years in (1, 3, 5):
        start = _value_on_or_before(series, _years_before(end_date, years)) if series[0][0] <= _years_before(end_date, years) else None
        if not start:
            out.append(None)
        elif years == 1:
            out.append(round((end_nav / start - 1) * 100, 2))
        else:
            out.append(round(((end_nav / start) ** (1 / years) - 1) * 100, 2))
    return tuple(out)


def _months_before(d, months):
    y, m = divmod(d.month - 1 - months, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return d.replace(year=y, month=m, day=day)


def _etf_prices(symbol):
    """(last close, close date, 1M %, 1Y %) from Dhan daily candles."""
    from dhanhq import dhanhq

    from connectors import dhan_connector

    resolved, _ = dhan_connector.resolve_security_ids([symbol])
    sid = resolved.get(symbol)
    if sid is None:
        raise RuntimeError(f"{symbol} not found")
    today = datetime.datetime.now(IST).date()
    resp = chart_connector._dhan().historical_daily_data(
        security_id=str(sid), exchange_segment=dhanhq.NSE, instrument_type="EQUITY",
        from_date=(today - datetime.timedelta(days=400)).isoformat(), to_date=today.isoformat(),
    )
    if resp.get("status") != "success":
        raise RuntimeError(f"{symbol}: {resp.get('remarks')}")
    d = resp["data"]
    series = sorted(
        (datetime.datetime.fromtimestamp(ts, IST).date(), float(c))
        for ts, c in zip(d["timestamp"], d["close"]) if float(c) > 0
    )
    if not series:
        raise RuntimeError(f"{symbol}: no candles")
    end_date, last = series[-1]
    pct = lambda start: round((last / start - 1) * 100, 2) if start else None
    return last, end_date, pct(_value_on_or_before(series, _months_before(end_date, 1))), pct(_value_on_or_before(series, _years_before(end_date, 1)))


def _fmt_date(d):
    return d.strftime("%-d %b %Y") if os.name != "nt" else d.strftime("%#d %b %Y")


def _refresh_fund(f, navs):
    code = str(f.get("amfiCode") or "")
    if code not in navs:
        raise RuntimeError(f"{f['id']}: AMFI code {code or '?'} not in today's NAV file")
    nav, nav_date = navs[code]
    r1, r3, r5 = returns_from_history(_nav_history(code))
    f.setdefault("aumDate", f.get("dataDate"))  # AUM/expense keep their own (older) date
    f.update(nav=nav, navDate=nav_date.isoformat(), dataDate=_fmt_date(nav_date), return1y=r1, cagr3y=r3, cagr5y=r5)


ETF_CALL_GAP_SECONDS = 1.5  # Dhan's data API rejects bursts (DH-904)
ETF_RATE_LIMIT_RETRIES = 3


def _refresh_etf(e, navs):
    code = str(e.get("amfiCode") or "")
    if code in navs:
        e["nav"] = navs[code][0]
    for attempt in range(ETF_RATE_LIMIT_RETRIES + 1):
        try:
            last, px_date, m1, y1 = _etf_prices(e["symbol"])
            break
        except Exception as exc:
            if "DH-904" not in str(exc) or attempt == ETF_RATE_LIMIT_RETRIES:
                raise
            time.sleep(5 * (attempt + 1))
    e.update(lastPrice=last, priceDate=px_date.isoformat(), change1m=m1, change1y=y1)
    return px_date


def _refresh_etfs(etfs, navs, failures):
    """Sequential, paced. Returns (price dates, failed symbols)."""
    px_dates, failed = [], []
    for i, e in enumerate(etfs):
        if i:
            time.sleep(ETF_CALL_GAP_SECONDS)
        try:
            px_dates.append(_refresh_etf(e, navs))
        except Exception as exc:
            failed.append(e["symbol"])
            failures.append(f"ETF {e['symbol']}: {exc}")
    return px_dates, failed


def _as_of(data, funds, etfs):
    nav_date = max(datetime.date.fromisoformat(f["navDate"]) for f in funds if f.get("navDate"))
    px = [datetime.date.fromisoformat(e["priceDate"]) for e in etfs if e.get("priceDate")]
    px_part = f" · ETF prices NSE close {_fmt_date(max(px))}" if px else ""
    data["asOf"] = f"NAV & returns as of {_fmt_date(nav_date)} (AMFI){px_part} · AUM & expense ratio as last updated"


def _write(data):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    client = chart_connector._s3()
    bucket = chart_connector._get_bucket(client)
    client.put_object(Bucket=bucket, Key=S3_KEY, Body=body, ContentType="application/json; charset=utf-8")
    cache.get_or_fetch(CACHE_KEY, CACHE_TTL_SECONDS, _load, force=True)


def refresh(force=False):
    """Refresh NAV/returns/ETF prices and write to S3. Returns a summary
    dict; skips (unless force) if already refreshed today (IST)."""
    today = datetime.datetime.now(IST).date()
    data = _load()
    funds = data["indexFunds"] + data["equityFunds"]
    etfs = [e for lst in data["etfs"].values() for e in lst]
    if data.get("refreshedOn") == today.isoformat() and not force:
        pending = set(data.get("etfPending") or [])
        if not pending:
            return {"skipped": True, "refreshedOn": data["refreshedOn"]}
        # Funds are done for today; retry only the ETFs that failed earlier.
        failures = []
        _, failed = _refresh_etfs([e for e in etfs if e["symbol"] in pending], _amfi_navs(), failures)
        data["etfPending"] = failed
        _as_of(data, funds, etfs)
        _write(data)
        return {"refreshedOn": data["refreshedOn"], "etfRetry": f"{len(pending) - len(failed)}/{len(pending)}", "failures": failures}

    navs = _amfi_navs()
    failures = []
    with ThreadPoolExecutor(max_workers=HISTORY_WORKERS) as pool:
        results = {f["id"]: pool.submit(_refresh_fund, f, navs) for f in funds}
    for fid, fut in results.items():
        try:
            fut.result()
        except Exception as exc:
            failures.append(f"{fid}: {exc}")
    ok_funds = len(funds) - len(failures)

    _, etf_failed = _refresh_etfs(etfs, navs, failures)

    if ok_funds < MIN_SUCCESS_SHARE * len(funds):
        raise RuntimeError(f"only {ok_funds}/{len(funds)} funds refreshed — not written. First failures: {failures[:5]}")

    _as_of(data, funds, etfs)
    data["etfPending"] = etf_failed  # retried on the next hourly check
    data["refreshedOn"] = today.isoformat()
    data["refreshedAt"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["refreshSources"] = [
        {"label": "NAV (daily)", "name": "AMFI NAV file", "url": "https://www.amfiindia.com/net-asset-value"},
        {"label": "1Y / 3Y / 5Y returns (daily, calculated from NAV history; 3Y/5Y annualised)", "name": "mfapi.in (AMFI data)", "url": "https://www.mfapi.in/"},
        {"label": "ETF last price, 1M / 1Y change (daily)", "name": "NSE close via Dhan", "url": None},
    ]
    data.pop("source", None)

    _write(data)
    return {"refreshedOn": data["refreshedOn"], "funds": f"{ok_funds}/{len(funds)}", "etfs": f"{len(etfs) - len(etf_failed)}/{len(etfs)}", "failures": failures}


# ---------------------------------------------------------------------
# Once-a-day runner (started by app.py)
# ---------------------------------------------------------------------
REFRESH_CHECK_SECONDS = 60 * 60
REFRESH_START_DELAY_SECONDS = 90  # let the app finish starting first


def _refresh_loop(log):
    time.sleep(REFRESH_START_DELAY_SECONDS)
    while True:
        try:
            result = refresh()
            if not result.get("skipped"):
                log(f"[mutual-funds] refreshed: {result}")
        except Exception as exc:
            log(f"[mutual-funds] daily refresh failed (keeping previous data): {exc}")
        # Hourly check: runs once per IST day (refreshedOn), retries any
        # ETFs that failed, and covers a backend left running past midnight.
        time.sleep(REFRESH_CHECK_SECONDS)


def start_daily_refresh(log=print):
    threading.Thread(target=_refresh_loop, args=(log,), daemon=True, name="mutual-funds-refresh").start()
