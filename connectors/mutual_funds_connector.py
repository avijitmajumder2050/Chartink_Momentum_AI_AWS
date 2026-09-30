"""Mutual Funds page data — kept as JSON in S3 at uploads/mutual_funds.json
(the copy bundled in the repo is the fallback if S3 is unreachable).

Rebuilt once a day by refresh() (started by app.py when the backend
starts). Which funds appear is decided from the data each day, not a fixed
list:

  * Equity funds — every Direct Growth scheme in AMFI's NAV file in the
    Large, Large & Mid, Mid, Small, Flexi, Multi Cap, Focused, ELSS,
    Value and Contra categories. 1Y / 3Y / 5Y returns are calculated from
    each fund's NAV history (mfapi.in, AMFI data); the top 5 per category
    by 5-year CAGR are shown (funds need 5 years of history).
  * Index funds — AMFI's equity index funds, best 5-year CAGR, one fund
    per tracked index.
  * ETFs — NSE's ETF list, grouped under the page's indices, most traded
    first; price, NAV and 1M / 1Y change from NSE's ETF market watch.
  * AUM, expense ratio, exit load, minimums, risk, lock-in — Groww, with
    INDmoney as fallback (connectors/mf_sources.py). Re-checked weekly per
    fund; a fund whose lookup fails keeps its last known figures.

Nothing is written if the fund universe or most return calculations fail;
the previous day's page stays up and the hourly check retries.
"""

import datetime
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from connectors import cache, chart_connector, mf_sources

S3_KEY = "uploads/mutual_funds.json"
LOCAL_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mutual_funds.json")
CACHE_KEY = "mutual_funds_snapshot"
CACHE_TTL_SECONDS = 60 * 60

MFAPI_URL = "https://api.mfapi.in/mf/{code}"
HTTP_HEADERS = mf_sources.HTTP_HEADERS
HTTP_TIMEOUT_SECONDS = 30
HISTORY_WORKERS = 4
# Write only if at least this share of return calculations succeeded — a
# source outage shouldn't replace good rankings with a half-empty set.
MIN_SUCCESS_SHARE = 0.6
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

TOP_PER_CATEGORY = 5
INDEX_FUNDS_SHOWN = 6
ETFS_PER_INDEX = 6
DETAILS_MAX_AGE_DAYS = 7
STALE_NAV_DAYS = 10  # a scheme whose NAV is older than this is closed/merged

# (substring of AMFI's category, page category) — order matters: "large &
# mid cap" must match before "large cap" and "mid cap".
EQUITY_CATEGORIES = [
    ("large & mid cap", "Large & Mid Cap"),
    ("large cap", "Large Cap"),
    ("mid cap", "Mid Cap"),
    ("small cap", "Small Cap"),
    ("flexi cap", "Flexi Cap"),
    ("multi cap", "Multi Cap"),
    ("focused", "Focused"),
    ("elss", "ELSS"),
    ("value", "Value"),
    ("contra", "Contra"),
]
CATEGORY_ORDER = ["Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap", "Flexi Cap", "Multi Cap", "Focused", "ELSS", "Value", "Contra"]

# Index funds whose names contain these aren't equity index funds.
NON_EQUITY_WORDS = (
    "gilt", "sdl", "g-sec", "gsec", "bond", "crisil", "ibx", "t-bill", "tbill", "liquid", "debt", "gold", "silver",
    "money market", "overnight", "aaa", "corporate", "elss", "fof", "fund of fund", "income", "treasury",
    "state development", "target maturity", "psu bank bond", "maturity", "g sec", "government",
    # overseas index funds — the page covers Indian indices
    "s&p", "nasdaq", "nyse", "fang", "world", "global", "hang seng", "taiwan", "japan", "china",
    " us ", "u.s.", "international", "developed", "emerging", "europe",
)

# NSE ETF "Underlying Key" (normalised) -> index name used on the page
# (the indices list, which matches sector_indices.csv).
ETF_INDEX_MAP = {
    "nifty50": "NIFTY", "niftybank": "BANKNIFTY", "niftyit": "NIFTYIT",
    "niftymidcap150": "NIFTY MIDCAP 150", "niftysmallcap250": "NIFTY SMALLCAP 250",
    "niftyauto": "NIFTY AUTO", "niftyprivatebank": "NIFTY PVT BANK", "nifty500": "NIFTY 500",
    "niftyfinancialservices": "FINNIFTY", "niftyfmcg": "NIFTY FMCG", "niftymetal": "NIFTY METAL",
    "niftypharma": "NIFTY PHARMA", "niftypsubank": "NIFTY PSU BANK", "niftyrealty": "NIFTY REALTY",
    "niftycommodities": "NIFTY COMMODITIES", "niftyindiaconsumption": "NIFTY CONSUMPTION",
    "niftypse": "NIFTYPSE", "niftyenergy": "NIFTY ENERGY", "niftyinfrastructure": "NIFTYINFRA",
    "niftymnc": "NIFTY MNC", "niftymncetf": "NIFTY MNC", "niftycpse": "NIFTYCPSE",
    "niftyservicessector": "NIFTY SERV SECTOR", "bsesensex": "SENSEX", "sensex": "SENSEX",
    "niftyhealthcare": "NIFTY HEALTHCARE", "nifty500multicap502525": "NIFTY500 MULTICAP",
    "niftyoilgas": "NIFTY OIL AND GAS", "niftyindiamanufacturing": "NIFTY INDIA MFG",
    "nifty200momentum30": "NIFTY200MOMENTM30", "niftyalphalowvolatility30": "NIFTY ALPHALOWVOL",
    "niftymidcap150momentum50": "NIFTYM150MOMNTM50", "niftyevandnewageautomotive": "NIFTY EV",
    "niftyindiadefence": "NIFTY IND DEFENCE", "nifty500momentum50": "NIFTY500MOMENTM50",
    "niftymicrocap250": "NIFTY MICROCAP250", "niftymidsmallcap400": "NIFTY MIDSMALLCAP 400",
    "niftyindiadigital": "NIFTY IND DIGITAL", "niftymedia": "NIFTY MEDIA",
    "niftyconsumerdurables": "NIFTY CONSR DURBL",
}


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
# Returns from NAV history
# ---------------------------------------------------------------------
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



def _fmt_date(d):
    return d.strftime("%-d %b %Y") if os.name != "nt" else d.strftime("%#d %b %Y")


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _equity_category(section):
    m = re.match(r"Equity Schemes?\s*-\s*(.*)", section, flags=re.I)
    if not m:
        return None
    s = m.group(1).lower()
    for needle, cat in EQUITY_CATEGORIES:
        if needle in s:
            return cat
    return None


def _is_equity_index_fund(s):
    sec = s["section"].lower()
    if "index fund" not in sec or "debt" in sec:
        return False
    name = s["name"].lower()
    return not any(w in name for w in NON_EQUITY_WORDS)


def _strip_amc(name, amc):
    """'Tata Nifty Midcap 150 Momentum 50 Index Fund', 'Tata' -> 'Nifty Midcap 150 Momentum 50'."""
    rest = name
    if amc and rest.lower().startswith(amc.lower()):
        rest = rest[len(amc):]
    elif amc and rest.split()[:1] and rest.split()[0].lower() == amc.split()[0].lower():
        rest = rest.split(None, 1)[1] if len(rest.split()) > 1 else rest
    rest = re.sub(r"\b(Index Fund|Index|Fund|ETF)\b", " ", rest, flags=re.I)
    return re.sub(r"\s+", " ", rest).strip(" -–")


def _cap_badges(index_name):
    k = _norm(index_name)
    badges = []
    if "largemidcap" in k:
        badges.append("Large & Mid Cap")
    elif "midsmallcap" in k:
        badges.append("Mid & Small Cap")
    elif "midcap" in k:
        badges.append("Mid Cap")
    elif "smallcap" in k:
        badges.append("Small Cap")
    elif "microcap" in k:
        badges.append("Micro Cap")
    elif any(x in k for x in ("nifty50", "nifty100", "next50", "sensex", "top10", "top15", "top20")):
        badges.append("Large Cap")
    elif "nifty500" in k or "totalmarket" in k:
        badges.append("Multi Cap")
    for word, badge in (("momentum", "Momentum"), ("value", "Value"), ("quality", "Quality"), ("alpha", "Alpha"),
                        ("lowvol", "Low Volatility"), ("equalweight", "Equal Weight")):
        if word in k:
            badges.append(badge)
    return badges


def _history_returns(codes):
    """{code: (1Y, 3Y, 5Y)} for the codes whose history loaded."""
    def one(code):
        return code, returns_from_history(_nav_history(code))

    out = {}
    with ThreadPoolExecutor(max_workers=HISTORY_WORKERS) as pool:
        for fut in [pool.submit(one, c) for c in codes]:
            try:
                code, r = fut.result()
                out[code] = r
            except Exception:
                continue
    return out


def _details(prev, today, lookups, force=False):
    """AUM / expense ratio / exit load / minimums / risk / lock-in / url.
    Reuses figures checked within the last week; otherwise tries each
    lookup in turn (Groww, then INDmoney), else keeps the last known
    figures. A failed lookup isn't retried until the next day."""
    prev = dict(prev or {})
    checked = prev.get("detailsOn")
    if not force and checked and prev.get("aumCr") is not None and (today - datetime.date.fromisoformat(checked)).days < DETAILS_MAX_AGE_DAYS:
        return prev
    if not force and prev.get("detailsTriedOn") == today.isoformat():
        return prev
    for lookup in lookups:
        try:
            fresh = lookup()
        except Exception:
            fresh = None
        if fresh:
            fresh["detailsOn"] = today.isoformat()
            return fresh
    prev["detailsTriedOn"] = today.isoformat()
    return prev


def _fund_record(s, kind, category, returns, det, index_name=None):
    r1, r3, r5 = returns
    det = det or {}
    lock = mf_sources.normalise_lock_in(det.get("lockIn")) if det.get("lockIn") else ("3 years" if category == "ELSS" else "None")
    checked = det.get("detailsOn")
    return {
        "id": f"mf-{s['code']}",
        "kind": kind,
        "name": det.get("fundName") or s["cleanName"],
        "amc": s["amc"],
        "category": category,
        "index": index_name,
        "capBadges": _cap_badges(index_name) if index_name else None,
        "aumCr": det.get("aumCr"),
        "aumDate": _fmt_date(datetime.date.fromisoformat(checked)) if checked else None,
        "expenseRatio": det.get("expenseRatio"),
        "return1y": r1,
        "cagr3y": r3,
        "cagr5y": r5,
        "risk": det.get("risk") or "—",
        "launch": det.get("launch"),
        "nav": s["nav"],
        "navDate": s["navDate"].isoformat(),
        "dataDate": _fmt_date(s["navDate"]),
        "exitLoad": det.get("exitLoad") or "—",
        "minLumpsum": det.get("minLumpsum"),
        "minSip": det.get("minSip"),
        "lockIn": lock,
        "note": None,
        "url": det.get("url") or f"https://www.amfiindia.com/net-asset-value",
        "amfiCode": s["code"],
        "detailsOn": checked,
        "detailsTriedOn": det.get("detailsTriedOn"),
        "detailsSource": det.get("detailsSource"),
    }


def _prev_by_code(prev):
    out = {}
    for f in prev.get("indexFunds", []) + prev.get("equityFunds", []):
        if f.get("amfiCode"):
            out[str(f["amfiCode"])] = f
    for lst in (prev.get("etfs") or {}).values():
        for e in lst:
            if e.get("symbol"):
                out[e["symbol"]] = e
    return out


def _build_etfs(schemes, prev_codes, today, log):
    """{page index: [etf]} from NSE's ETF list and market watch."""
    by_isin = {}
    for s in schemes:
        for isin in s["isins"]:
            by_isin.setdefault(isin, s)
    quotes = mf_sources.nse_etf_quotes()
    groups = {}
    for row in mf_sources.nse_etf_list():
        if row["kind"].upper() != "EQUITY":
            continue
        ix = ETF_INDEX_MAP.get(_norm(row["underlying"]))
        q = quotes.get(row["symbol"])
        if not ix or not q:
            continue
        groups.setdefault(ix, []).append((row, q))
    out = {}
    for ix, rows in groups.items():
        rows.sort(key=lambda rq: rq[1]["tradedValue"] or 0, reverse=True)
        lst = []
        for row, q in rows[:ETFS_PER_INDEX]:
            s = by_isin.get(row["isin"])
            code = s["code"] if s else None
            name = mf_sources.clean_fund_name(s["name"]) if s else row["securityName"]
            prev = prev_codes.get(row["symbol"])
            det = _details(prev, today, [
                lambda r=row: mf_sources.groww_etf_details(r["symbol"], r["isin"]),
                lambda p=prev: mf_sources.indmoney_details("", p.get("url")) if p and "indmoney.com/etfs" in (p.get("url") or "") else None,
            ])
            lst.append({
                "symbol": row["symbol"],
                "name": name,
                "amc": s["amc"] if s else "",
                "lastPrice": q["lastPrice"],
                "nav": q["nav"],
                "priceDate": q["priceDate"],
                "change1m": q["change1m"],
                "change1y": q["change1y"],
                "tradedValueCr": round((q["tradedValue"] or 0) / 1e7, 2),
                "aumCr": det.get("aumCr"),
                "expenseRatio": det.get("expenseRatio"),
                "url": det.get("url") or f"https://www.nseindia.com/get-quotes/equity?symbol={row['symbol']}",
                "amfiCode": code,
                "detailsOn": det.get("detailsOn"),
                "detailsTriedOn": det.get("detailsTriedOn"),
                "detailsSource": det.get("detailsSource"),
            })
        out[ix] = lst
    if len(out) < 5:
        raise RuntimeError(f"only {len(out)} indices have ETFs — NSE data looks incomplete")
    log(f"[mutual-funds] ETFs: {sum(len(v) for v in out.values())} across {len(out)} indices")
    return out


def build(prev, today=None, log=print, force_details=False):
    """The page data, rebuilt from the sources. `prev` is the current data
    (for last-known details and the indices list). Raises if the fund
    universe or most return calculations fail."""
    today = today or datetime.datetime.now(IST).date()
    prev_codes = _prev_by_code(prev)
    pending = set()

    schemes = mf_sources.amfi_schemes()
    latest = max(s["navDate"] for s in schemes)
    fresh = [s for s in schemes if (latest - s["navDate"]).days <= STALE_NAV_DAYS and mf_sources.is_direct_growth(s)]
    for s in fresh:
        s["cleanName"] = mf_sources.clean_fund_name(s["name"])

    equity, index = {}, []
    seen = set()
    for s in fresh:
        key = (s["section"], _norm(s["cleanName"]))
        if key in seen:
            continue
        seen.add(key)
        cat = _equity_category(s["section"])
        if cat:
            equity.setdefault(cat, []).append(s)
        elif _is_equity_index_fund(s):
            index.append(s)
    candidates = [s for lst in equity.values() for s in lst] + index
    log(f"[mutual-funds] universe: {len(candidates)} direct-growth funds ({sum(len(v) for v in equity.values())} equity in {len(equity)} categories, {len(index)} index)")

    returns = _history_returns([s["code"] for s in candidates])
    if len(returns) < MIN_SUCCESS_SHARE * len(candidates):
        raise RuntimeError(f"NAV history loaded for only {len(returns)}/{len(candidates)} funds — not written")

    def with_5y(lst):
        ranked = [s for s in lst if (returns.get(s["code"]) or (None, None, None))[2] is not None]
        return sorted(ranked, key=lambda s: returns[s["code"]][2], reverse=True)

    def details_for(s):
        prev_f = prev_codes.get(s["code"])
        return _details(prev_f, today, [
            lambda: mf_sources.groww_details(s["code"], s["cleanName"]),
            lambda: mf_sources.indmoney_details(s["cleanName"], (prev_f or {}).get("url")),
        ], force=force_details)

    equity_funds = []
    for cat in CATEGORY_ORDER:
        for s in with_5y(equity.get(cat, []))[:TOP_PER_CATEGORY]:
            equity_funds.append(_fund_record(s, "Equity MF", cat, returns[s["code"]], details_for(s)))

    index_funds, tracked = [], set()
    for s in with_5y(index):
        ix_name = _strip_amc(s["cleanName"], s["amc"])
        k = _norm(ix_name)
        if not k or k in tracked:
            continue
        tracked.add(k)
        index_funds.append(_fund_record(s, "Index Fund", "Index Fund", returns[s["code"]], details_for(s), index_name=ix_name))
        if len(index_funds) >= INDEX_FUNDS_SHOWN:
            break

    try:
        etfs = _build_etfs(schemes, prev_codes, today, log)
    except Exception as exc:
        log(f"[mutual-funds] ETFs not refreshed, keeping previous: {exc}")
        etfs = prev.get("etfs") or {}
        pending.add("etfs")

    linked = {}
    for f in index_funds:
        page_ix = ETF_INDEX_MAP.get(_norm(f["index"]))
        if page_ix and page_ix not in linked:
            linked[page_ix] = f["id"]

    px_dates = [e["priceDate"] for lst in etfs.values() for e in lst if e.get("priceDate")]
    px_part = f" · ETF prices NSE close {_fmt_date(datetime.date.fromisoformat(max(px_dates)))}" if px_dates else ""
    data = {
        "title": prev.get("title") or "Mutual Funds",
        "asOf": f"NAV & returns as of {_fmt_date(latest)} (AMFI){px_part} · AUM & expense ratio checked weekly",
        "indexFunds": index_funds,
        "equityCategories": [c for c in CATEGORY_ORDER if any(f["category"] == c for f in equity_funds)],
        "equityFunds": equity_funds,
        "etfs": etfs,
        "indices": prev.get("indices") or [],
        "linkedIndexFunds": linked,
        "notInvestable": prev.get("notInvestable") or {},
        "selection": {
            "equity": f"Top {TOP_PER_CATEGORY} Direct Growth funds per category by 5-year CAGR, from {sum(len(v) for v in equity.values())} funds",
            "index": f"Best 5-year CAGR, one fund per index, from {len(index)} equity index funds",
            "etf": f"Up to {ETFS_PER_INDEX} ETFs per index, most traded first",
        },
        "refreshedOn": today.isoformat(),
        "refreshedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pending": sorted(pending),
        "sources": [
            {"label": "Fund list, categories and daily NAV", "name": "AMFI NAV file", "url": "https://www.amfiindia.com/net-asset-value"},
            {"label": "1Y / 3Y / 5Y returns (calculated from NAV history; 3Y/5Y annualised)", "name": "mfapi.in (AMFI data)", "url": "https://www.mfapi.in/"},
            {"label": "AUM, expense ratio, exit load, minimums, risk, lock-in", "name": "Groww fund pages (INDmoney as fallback)", "url": "https://groww.in/mutual-funds"},
            {"label": "ETF list, last price, NAV, 1M and 1Y change", "name": "NSE ETF market watch", "url": "https://www.nseindia.com/market-data/exchange-traded-funds-etf"},
        ],
    }
    summary = {
        "refreshedOn": data["refreshedOn"],
        "equity": f"{len(equity_funds)} funds / {len(data['equityCategories'])} categories",
        "index": len(index_funds),
        "etfs": sum(len(v) for v in etfs.values()),
        "returnsLoaded": f"{len(returns)}/{len(candidates)}",
        "pending": data["pending"],
    }
    return data, summary


def _write(data):
    data.pop("source", None)  # set by _load(); not part of the stored file
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    client = chart_connector._s3()
    bucket = chart_connector._get_bucket(client)
    client.put_object(Bucket=bucket, Key=S3_KEY, Body=body, ContentType="application/json; charset=utf-8")
    cache.get_or_fetch(CACHE_KEY, CACHE_TTL_SECONDS, _load, force=True)


def refresh(force=False, log=print):
    """Rebuild and write to S3. Once per IST day; the same day again only
    if the ETF section failed (pending), or with force."""
    today = datetime.datetime.now(IST).date()
    prev = _load()
    if prev.get("refreshedOn") == today.isoformat() and not prev.get("pending") and not force:
        return {"skipped": True, "refreshedOn": prev["refreshedOn"]}
    data, summary = build(prev, today, log=log)
    _write(data)
    return summary


# ---------------------------------------------------------------------
# Once-a-day runner (started by app.py)
# ---------------------------------------------------------------------
REFRESH_CHECK_SECONDS = 60 * 60
REFRESH_START_DELAY_SECONDS = 90  # let the app finish starting first


def _refresh_loop(log):
    time.sleep(REFRESH_START_DELAY_SECONDS)
    while True:
        try:
            result = refresh(log=log)
            if not result.get("skipped"):
                log(f"[mutual-funds] refreshed: {result}")
        except Exception as exc:
            log(f"[mutual-funds] daily refresh failed (keeping previous data): {exc}")
        # Hourly check: rebuilds once per IST day, retries anything left
        # pending, and covers a backend left running past midnight.
        time.sleep(REFRESH_CHECK_SECONDS)


def start_daily_refresh(log=print):
    threading.Thread(target=_refresh_loop, args=(log,), daemon=True, name="mutual-funds-refresh").start()
