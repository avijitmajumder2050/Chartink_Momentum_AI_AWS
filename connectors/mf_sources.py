"""Fetchers behind the Mutual Funds page's daily rebuild
(mutual_funds_connector.refresh()). Each returns plain dicts; ranking and
selection live in mutual_funds_connector.

  * AMFI NAVAll.txt — every open-ended scheme with its SEBI category, AMC,
    ISINs and latest NAV. This is the fund universe.
  * Groww scheme API — AUM, expense ratio, exit load, minimums, launch
    date, riskometer, lock-in. Matched to AMFI by scheme code, so a search
    hit for a similarly named fund is never used.
  * INDmoney fund page — fallback for the same fields when Groww has no
    match (its key-facts line is parsed from the page text).
  * NSE — ETF list (symbol, ISIN, underlying index) and ETF market watch
    (last price, NAV, 30-day / 365-day change, traded value).
"""

import csv
import datetime
import io
import re
import time

import requests

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
HTTP_TIMEOUT_SECONDS = 30

AMFI_NAV_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
GROWW_SEARCH_URL = "https://groww.in/v1/api/search/v3/query/global/st_query"
GROWW_SCHEME_URL = "https://groww.in/v1/api/data/mf/web/v2/scheme/search/{search_id}"
GROWW_PAGE_URL = "https://groww.in/mutual-funds/{search_id}"
GROWW_ETF_PAGE_URL = "https://groww.in/etfs/{search_id}"
INDMONEY_URL = "https://www.indmoney.com/mutual-funds/{slug}"
NSE_HOME_URL = "https://www.nseindia.com/"
NSE_ETF_API_URL = "https://www.nseindia.com/api/etf"
NSE_ETF_LIST_URL = "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"

# Words in a scheme name/plan that mean "not the Direct Growth plan".
_NOT_GROWTH = ("idcw", "dividend", "bonus", "payout", "reinvest", "segregated", "income distribution")


# ---------------------------------------------------------------------
# AMFI
# ---------------------------------------------------------------------
def amfi_schemes():
    """Every scheme line in AMFI's NAV file:
    [{code, isins, name, plan, option, nav, navDate, section, amc}].
    File layout: a section header like "Open Ended Schemes(Equity Scheme -
    Large Cap Fund)", then an AMC line ("Axis Mutual Fund"), then
    code;ISIN growth;ISIN reinvest;name;plan;option;NAV;date lines."""
    resp = requests.get(AMFI_NAV_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    section = amc = None
    out = []
    for raw in resp.text.splitlines():
        line = raw.strip()
        if not line or line.startswith("Scheme Code"):
            continue
        m = re.match(r"^(Open Ended|Close Ended|Interval Fund) Schemes\s*\((.*)\)$", line)
        if m:
            section = m.group(2).strip()
            continue
        p = line.split(";")
        if len(p) < 8:
            if ";" not in line:
                amc = re.sub(r"\s+Mutual Fund$", "", line, flags=re.I).strip()
            continue
        if not p[0].strip().isdigit():
            continue
        try:
            nav = float(p[-2])
            nav_date = datetime.datetime.strptime(p[-1].strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        out.append({
            "code": p[0].strip(),
            "isins": [x.strip() for x in p[1:3] if x.strip() and x.strip() != "-"],
            "name": p[3].strip(),
            "plan": p[4].strip() if len(p) >= 8 else "",
            "option": p[5].strip() if len(p) >= 8 else "",
            "nav": nav,
            "navDate": nav_date,
            "section": section or "",
            "amc": amc or "",
        })
    if len(out) < 1000:
        raise RuntimeError(f"AMFI NAV file looks incomplete ({len(out)} schemes)")
    return out


def is_direct_growth(s):
    text = f"{s['name']} {s['plan']} {s['option']}".lower()
    return "direct" in text and "growth" in text and not any(w in text for w in _NOT_GROWTH)


def clean_fund_name(name):
    """'Axis Small Cap Fund - Direct Plan - Growth' -> 'Axis Small Cap Fund'."""
    name = re.split(r"\s*[-–(]?\s*\b(Direct|Regular)\b", name, maxsplit=1, flags=re.I)[0]
    return re.sub(r"[\s\-–]+$", "", name).strip()


# ---------------------------------------------------------------------
# Groww (primary for AUM / expense ratio / exit load / minimums / risk)
# ---------------------------------------------------------------------
def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _groww_scheme(search_id):
    resp = requests.get(GROWW_SCHEME_URL.format(search_id=search_id), headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _groww_candidates(name):
    """Groww search_ids for a fund name, best match first. The slug guess
    (Groww's usual '<name>-direct-growth') is tried before the search."""
    ids = [f"{_slug(name)}-direct-growth"]
    try:
        resp = requests.get(
            GROWW_SEARCH_URL,
            params={"page": 0, "query": f"{name} Direct Growth", "size": 6, "web": "true"},
            headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS,
        )
        for c in (resp.json().get("data") or {}).get("content") or []:
            if c.get("entity_type") == "Scheme" and c.get("search_id") and c["search_id"] not in ids:
                ids.append(c["search_id"])
    except (requests.RequestException, ValueError):
        pass
    return ids[:3]


def _parse_date(text, fmts=("%d-%b-%Y", "%d %B, %Y", "%d-%m-%Y")):
    for fmt in fmts:
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _lock_in_text(years):
    if not years:
        return "None"
    return f"{years:g} year" + ("" if years == 1 else "s")


def normalise_lock_in(text):
    """'3 Years' / '3 years' / 'No Lock-in' -> '3 years' / 'None'."""
    if not text or "no lock" in text.lower() or text.strip().lower() in ("none", "nil", "-"):
        return "None"
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(year|yr|month|day)", text, flags=re.I)
    if not m:
        return text.strip()
    n, unit = float(m.group(1)), {"yr": "year"}.get(m.group(2).lower(), m.group(2).lower())
    return f"{n:g} {unit}" + ("" if n == 1 else "s")


def groww_details(code, name, gap=0.4):
    """Details for AMFI scheme `code` from Groww, or None. Only a Groww
    page whose scheme_code (or direct_scheme_code) equals `code` counts."""
    for sid in _groww_candidates(name):
        time.sleep(gap)
        d = _groww_scheme(sid)
        if not d or str(code) not in (str(d.get("scheme_code")), str(d.get("direct_scheme_code"))):
            continue
        stats = (d.get("return_stats") or [{}])[0] or {}
        lock = d.get("lock_in") or {}
        lock_years = lock.get("years") or ((d.get("additional_details") or {}).get("lock_in_yrs"))
        launch = _parse_date(d.get("launch_date") or "")
        try:
            er = float(d["expense_ratio"]) if d.get("expense_ratio") not in (None, "") else None
        except (TypeError, ValueError):
            er = None
        return {
            "aumCr": round(float(d["aum"]), 2) if d.get("aum") is not None else None,
            "expenseRatio": er,
            "exitLoad": (d.get("exit_load") or "").strip() or None,
            "minLumpsum": d.get("min_investment_amount"),
            "minSip": d.get("min_sip_investment"),
            "risk": stats.get("risk") or None,
            "lockIn": _lock_in_text(lock_years),
            "launch": launch.strftime("%d %b %Y").lstrip("0") if launch else None,
            "benchmark": d.get("benchmark_name") or d.get("benchmark"),
            "fundName": clean_fund_name(d.get("fund_name") or "") or None,
            "url": GROWW_PAGE_URL.format(search_id=d.get("search_id") or sid),
            "detailsSource": "Groww",
        }
    return None


def groww_etf_details(symbol, isin, gap=0.4):
    """AUM / expense ratio for an NSE ETF from its Groww ETF page, or None.
    The Groww search hit must carry this NSE symbol, and the page's own
    fundamentals block (not a peer's) must carry this ISIN."""
    try:
        resp = requests.get(
            GROWW_SEARCH_URL, params={"page": 0, "query": symbol, "size": 6, "web": "true"},
            headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS,
        )
        hits = [c for c in (resp.json().get("data") or {}).get("content") or []
                if c.get("entity_type") == "ETF" and (c.get("nse_scrip_code") or "").upper() == symbol.upper()]
    except (requests.RequestException, ValueError):
        return None
    for c in hits[:2]:
        time.sleep(gap)
        try:
            page = requests.get(GROWW_ETF_PAGE_URL.format(search_id=c["search_id"]), headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
        except requests.RequestException:
            continue
        m = re.search(r'"fundamentalsData":\{"isin":"([A-Z0-9]+)"[^}]*?"aumInCrores":([\d.]+)[^}]*?"expenseRatio":([\d.]+)', page.text)
        if not m or (isin and m.group(1) != isin):
            continue
        return {
            "aumCr": round(float(m.group(2)), 2),
            "expenseRatio": float(m.group(3)),
            "url": GROWW_ETF_PAGE_URL.format(search_id=c["search_id"]),
            "detailsSource": "Groww",
        }
    return None


# ---------------------------------------------------------------------
# INDmoney (fallback)
# ---------------------------------------------------------------------
def _num(text):
    try:
        return float(text.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def indmoney_details(name, url=None):
    """Key facts from an INDmoney fund page, or None. Tries `url` (a known
    INDmoney link) first, then the usual slugs for the fund name."""
    urls = [url] if url and "indmoney.com" in url else []
    urls += [INDMONEY_URL.format(slug=f"{_slug(name)}-{suffix}") for suffix in ("direct-growth", "direct-plan-growth", "direct-plan-growth-plan")]
    for u in urls:
        try:
            resp = requests.get(u, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and len(resp.text) < 50_000:
            return None  # bot check — every other slug would get the same
        if resp.status_code != 200:
            continue
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text, flags=re.S)
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        er = re.search(r"Expense ratio ([\d.]+)%", t)
        aum = re.search(r"AUM ₹\s?([\d,.]+)\s?Cr", t)
        if not (er or aum):
            continue
        mins = re.search(r"Min Lumpsum/SIP ₹([\d,]+)/₹([\d,]+)", t)
        exit_load = re.search(r"Exit Load (.+?) Lock In", t)
        lock = re.search(r"Lock In (.+?) (?:TurnOver|Risk)", t)
        risk = re.search(r"Risk (Low|Low to Moderate|Moderate|Moderately High|High|Very High) Risk", t)
        launch = re.search(r"Inception Date (\d{1,2} \w+, \d{4})", t)
        launch_d = _parse_date(launch.group(1)) if launch else None
        lock_text = lock.group(1).strip() if lock else None
        return {
            "aumCr": _num(aum.group(1)) if aum else None,
            "expenseRatio": _num(er.group(1)) if er else None,
            "exitLoad": exit_load.group(1).strip() if exit_load else None,
            "minLumpsum": _num(mins.group(1)) if mins else None,
            "minSip": _num(mins.group(2)) if mins else None,
            "risk": risk.group(1) if risk else None,
            "lockIn": normalise_lock_in(lock_text),
            "launch": launch_d.strftime("%d %b %Y").lstrip("0") if launch_d else None,
            "url": u,
            "detailsSource": "INDmoney",
        }
    return None


# ---------------------------------------------------------------------
# NSE ETFs
# ---------------------------------------------------------------------
def _nse_session():
    s = requests.Session()
    s.headers.update({**HTTP_HEADERS, "Accept-Language": "en-US,en;q=0.9"})
    s.get(NSE_HOME_URL, timeout=HTTP_TIMEOUT_SECONDS)  # sets the cookies the API needs
    return s


def nse_etf_list():
    """[{symbol, isin, underlying, kind}] from NSE's ETF security list."""
    resp = requests.get(NSE_ETF_LIST_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    out = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        if row.get("Symbol"):
            out.append({
                "symbol": row["Symbol"],
                "isin": row.get("ISINNumber", ""),
                "underlying": row.get("Underlying Key", ""),
                "kind": row.get("ETF Underlying", ""),
                "securityName": row.get("SecurityName", ""),
            })
    if len(out) < 50:
        raise RuntimeError(f"NSE ETF list looks incomplete ({len(out)} rows)")
    return out


def nse_etf_quotes():
    """{symbol: {lastPrice, nav, change1m, change1y, tradedValue, priceDate}}
    from NSE's ETF market watch (one call for every ETF)."""
    s = _nse_session()
    s.headers.update({"Accept": "application/json", "Referer": "https://www.nseindia.com/market-data/exchange-traded-funds-etf"})
    resp = s.get(NSE_ETF_API_URL, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    stamp = _parse_date((body.get("timestamp") or "")[:11], ("%d-%b-%Y",))
    out = {}
    for r in body.get("data") or []:
        out[r["symbol"]] = {
            "lastPrice": _num(str(r.get("ltP"))),
            "nav": _num(str(r.get("nav"))),
            "change1m": r.get("perChange30d"),
            "change1y": r.get("perChange365d"),
            "tradedValue": _num(str(r.get("trdVal"))) or 0,
            "priceDate": stamp.isoformat() if stamp else None,
        }
    if len(out) < 50:
        raise RuntimeError(f"NSE ETF market watch looks incomplete ({len(out)} rows)")
    return out
