"""Fundamentals connector — scrapes screener.in company pages.

Unlike the IPO sources, screener.in is fully server-rendered (confirmed by
fetching a page with plain `requests` and finding clean `<table>` markup
under `<section id="quarters/profit-loss/balance-sheet/cash-flow/ratios/
shareholding">`), so no headless browser is needed here.

Peer comparison is NOT scraped — screener.in loads that table via a
separate authenticated-feeling AJAX call keyed by an internal numeric
company id that isn't worth reverse-engineering for this pass. Rather
than borrow a mock, always-wrong-for-most-symbols peer list, the
research page simply omits that section — see templates/research.html.
"""

import re

import requests
from bs4 import BeautifulSoup

from connectors import cache
from connectors.format_utils import change_color, initials, inr_crores, sparkline_points

BASE_URL = "https://www.screener.in/company/{symbol}/consolidated/"
FALLBACK_URL = "https://www.screener.in/company/{symbol}/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

CACHE_TTL_SECONDS = 12 * 60 * 60

# screener.in's own price chart calls this JSON endpoint client-side (found
# by capturing the page's network requests with Playwright — it's not
# documented, but it's public, needs no auth, and works with plain
# `requests`). EOD daily closes only, no intraday, so there's no real "1D"
# view. The API adapts resolution to the requested `days` — a 30-day
# request returns real daily bars, but a 1825-day request comes back
# weekly-sampled — so each period tab needs its own request at its own
# `days` value rather than slicing one big fetch.
CHART_API_URL = "https://www.screener.in/api/company/{company_id}/chart/?q=Price&days={days}&consolidated=true"
PRICE_CACHE_TTL_SECONDS = 6 * 60 * 60
CHART_PERIODS = [
    ("1M", 30),
    ("6M", 182),
    ("1Y", 365),
    ("3Y", 1095),
    ("5Y", 1825),
]

YEAR_COLUMN = re.compile(r"^[A-Za-z]{3}\s\d{4}$")

SHAREHOLDING_COLORS = {
    "Promoters": "#4640DE",
    "FIIs": "#17A673",
    "DIIs": "#B98A2E",
    "Government": "#8A90A0",
    "Public": "#D8DAE3",
    "Others": "#D8DAE3",
}

FISCAL_Q = {3: 4, 6: 1, 9: 2, 12: 3}


def _clean_num(text):
    if text is None:
        return None
    text = text.strip().replace(",", "").replace("%", "").replace("₹", "")
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _year_columns(headers):
    """Indices+labels of columns that are real period columns (year or
    TTM) — screener tacks non-period columns (Raw PDF link, Dividend
    Payout %) onto the end of some tables, this filters those out."""
    result = []
    for i, h in enumerate(headers):
        if YEAR_COLUMN.match(h) or h == "TTM":
            result.append((i, h))
    return result


def _table_rows(soup, section_id):
    section = soup.find("section", id=section_id)
    table = section.find("table") if section else None
    if table is None:
        return {}, []

    headers = [th.get_text(strip=True) for th in table.find_all("th")][1:]
    year_cols = _year_columns(headers)

    body = table.find("tbody") or table
    rows = {}
    for tr in body.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True).rstrip("+").strip()
        if not label:
            continue
        values = [cells[i + 1].get_text(strip=True) for i, _ in year_cols if i + 1 < len(cells)]
        rows[label] = values

    return rows, [h for _, h in year_cols]


def _header_info(soup):
    """Company name + last close price/change from the desktop page header
    (`<h1>` + sibling price block) — screener.in doesn't expose intraday
    quotes, so `price` here is the last close, not a live tick."""
    h1 = None
    for candidate in soup.find_all("h1"):
        if "show-from-tablet-landscape" in (candidate.get("class") or []):
            h1 = candidate
            break
    h1 = h1 or soup.find("h1")

    name = h1.get_text(strip=True) if h1 else "Unknown"

    price, change_pct, direction = None, None, None
    price_block = h1.find_parent().find(class_="font-size-18") if h1 else None
    if price_block:
        price_span = price_block.find("span")
        if price_span:
            price = price_span.get_text(strip=True)
        change_span = price_block.find(class_=re.compile(r"\b(up|down)\b"))
        if change_span:
            change_pct = change_span.get_text(strip=True)
            direction = "up" if "up" in (change_span.get("class") or []) else "down"

    return {
        "name": name,
        "initials": initials(name),
        "price": price or "-",
        "changePct": change_pct or "-",
        "direction": direction or "up",
    }


def _top_ratios(soup):
    ul = soup.find("ul", id="top-ratios")
    if ul is None:
        return {}
    out = {}
    for li in ul.find_all("li"):
        name = li.find("span", class_="name")
        value = li.find("span", class_="value")
        if name and value:
            # collapse the stray spaces get_text(" ") inserts between the currency symbol/number/unit
            out[name.get_text(strip=True)] = re.sub(r"\s+", "", value.get_text(" ", strip=True))
    return out


def _fetch_raw(symbol):
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    soup = None
    for url_template in (BASE_URL, FALLBACK_URL):
        resp = session.get(url_template.format(symbol=symbol), timeout=15)
        if resp.status_code != 200:
            continue
        candidate = BeautifulSoup(resp.text, "lxml")
        if candidate.find("section", id="quarters"):
            soup = candidate
            break

    if soup is None:
        raise RuntimeError(f"screener.in has no data for symbol {symbol!r}")

    company_id_tag = soup.find(attrs={"data-company-id": True})

    return {
        "header": _header_info(soup),
        "company_id": company_id_tag["data-company-id"] if company_id_tag else None,
        "top_ratios": _top_ratios(soup),
        "quarters": _table_rows(soup, "quarters"),
        "profit_loss": _table_rows(soup, "profit-loss"),
        "balance_sheet": _table_rows(soup, "balance-sheet"),
        "cash_flow": _table_rows(soup, "cash-flow"),
        "ratios": _table_rows(soup, "ratios"),
        "shareholding": _table_rows(soup, "shareholding"),
    }


def _get_raw(symbol):
    key = f"screener_raw_{symbol.upper()}"
    return cache.get_or_fetch(key, CACHE_TTL_SECONDS, lambda: _fetch_raw(symbol))


def _quarter_label(year_header):
    month_name, year = year_header.split()
    month_num = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }[month_name]
    fy = int(year) if month_num <= 3 else int(year) + 1
    return f"Q{FISCAL_Q.get(month_num, 1)} FY{str(fy)[2:]}"


def get_research_data(symbol):
    raw = _get_raw(symbol)
    fundamentals = [{"label": label, "value": value} for label, value in raw["top_ratios"].items()]

    return {
        "symbol": symbol.upper(),
        "header": raw["header"],
        "fundamentals": fundamentals,
    }


def get_fundamentals_data(symbol):
    raw = _get_raw(symbol)

    pl_rows, pl_years = raw["profit_loss"]
    annual_years = [y for y in pl_years if y != "TTM"][-5:]

    def pl_slice(label):
        values = pl_rows.get(label, [])
        idxs = [pl_years.index(y) for y in annual_years if y in pl_years]
        return [values[i] if i < len(values) else "" for i in idxs]

    fy_keys = ["fy22", "fy23", "fy24", "fy25", "fy26"]
    plRows = []
    for label, row_key, weight in [
        ("Revenue", "Sales", "400"),
        ("Operating profit", "Operating Profit", "400"),
        ("OPM %", "OPM %", "400"),
        ("Net profit", "Net Profit", "700"),
        ("EPS (₹)", "EPS in Rs", "400"),
    ]:
        values = pl_slice(row_key)
        if not any(values):
            continue
        row = {"label": label, "weight": weight}
        for k, v in zip(fy_keys[-len(values):], values):
            row[k] = v
        plRows.append(row)

    bs_rows, bs_years = raw["balance_sheet"]
    balanceSheet = []
    if bs_years:
        total_assets = _clean_num((bs_rows.get("Total Assets") or [""])[-1])
        equity_capital = _clean_num((bs_rows.get("Equity Capital") or [""])[-1]) or 0
        reserves = _clean_num((bs_rows.get("Reserves") or [""])[-1]) or 0
        shareholder_equity = equity_capital + reserves
        if total_assets is not None:
            balanceSheet.append({"label": "Total assets", "value": inr_crores(total_assets)})
            balanceSheet.append({"label": "Total liabilities", "value": inr_crores(total_assets - shareholder_equity)})
        balanceSheet.append({"label": "Shareholder equity", "value": inr_crores(shareholder_equity)})

    cf_rows, cf_years = raw["cash_flow"]
    cashFlow = []
    for row_key, label in [
        ("Cash from Operating Activity", "Operating activities"),
        ("Cash from Investing Activity", "Investing activities"),
        ("Cash from Financing Activity", "Financing activities"),
    ]:
        values = cf_rows.get(row_key, [])
        val = _clean_num(values[-1]) if values else None
        if val is None:
            continue
        sign = "+" if val >= 0 else "-"
        cashFlow.append({"label": label, "value": f"{sign}₹{abs(val):,.0f} Cr", "color": change_color(val)})

    quarters_rows, quarters_years = raw["quarters"]
    quarters = []
    recent_years = quarters_years[-6:]
    net_profit_values = quarters_rows.get("Net Profit", [])
    for i, year_header in enumerate(recent_years):
        idx = quarters_years.index(year_header)
        revenue = (quarters_rows.get("Sales") or [""])[idx] if idx < len(quarters_rows.get("Sales", [])) else ""
        profit = net_profit_values[idx] if idx < len(net_profit_values) else ""
        eps = (quarters_rows.get("EPS in Rs") or [""])[idx] if idx < len(quarters_rows.get("EPS in Rs", [])) else ""

        yoy_idx = idx - 4
        yoy = "-"
        yoy_color = "#5B6270"
        if 0 <= yoy_idx < len(net_profit_values):
            current = _clean_num(profit)
            prior = _clean_num(net_profit_values[yoy_idx])
            if current is not None and prior:
                pct = (current - prior) / abs(prior) * 100
                yoy = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
                yoy_color = change_color(pct)

        quarters.append({
            "label": _quarter_label(year_header),
            "revenue": revenue,
            "profit": profit,
            "eps": eps,
            "yoy": yoy,
            "yoyColor": yoy_color,
        })
    quarters.reverse()

    ratios_rows, ratios_years = raw["ratios"]
    ratios = []

    def add_ratio(label, values_by_year, years, suffix=""):
        aligned = [(y, v) for y, v in zip(years, values_by_year) if _clean_num(v) is not None][-5:]
        if len(aligned) < 2:
            return
        nums = [_clean_num(v) for _, v in aligned]
        ratios.append({
            "label": label,
            "current": f"{nums[-1]:.1f}{suffix}",
            "points": sparkline_points(nums),
        })

    if "ROCE %" in ratios_rows:
        add_ratio("ROCE %", ratios_rows["ROCE %"], ratios_years, "%")
    if "OPM %" in pl_rows:
        add_ratio("OPM %", pl_rows["OPM %"], pl_years, "%")

    equity_by_year = {}
    for y in bs_years:
        i = bs_years.index(y)
        ec = _clean_num((bs_rows.get("Equity Capital") or [None] * len(bs_years))[i]) if i < len(bs_rows.get("Equity Capital", [])) else None
        rs = _clean_num((bs_rows.get("Reserves") or [None] * len(bs_years))[i]) if i < len(bs_rows.get("Reserves", [])) else None
        if ec is not None and rs is not None:
            equity_by_year[y] = ec + rs

    # non-bank companies label this row "Borrowings"; banks (different
    # balance-sheet template on screener.in) label it "Borrowing" (singular)
    borrowings_key = "Borrowings" if "Borrowings" in bs_rows else "Borrowing" if "Borrowing" in bs_rows else None
    if borrowings_key:
        de_years, de_values = [], []
        for y, borrow_text in zip(bs_years, bs_rows[borrowings_key]):
            borrow = _clean_num(borrow_text)
            eq = equity_by_year.get(y)
            if borrow is not None and eq:
                de_years.append(y)
                de_values.append(f"{borrow / eq:.2f}")
        if de_values:
            add_ratio("Debt / Equity", de_values, de_years)

    if "Net Profit" in pl_rows:
        roe_years, roe_values = [], []
        for y, np_text in zip(pl_years, pl_rows["Net Profit"]):
            net_profit = _clean_num(np_text)
            eq = equity_by_year.get(y)
            if net_profit is not None and eq:
                roe_years.append(y)
                roe_values.append(f"{net_profit / eq * 100:.1f}")
        if roe_values:
            add_ratio("ROE %", roe_values, roe_years, "%")

    ratios = ratios[:4]

    sh_rows, sh_years = raw["shareholding"]
    shareholding = []
    for label, values in sh_rows.items():
        if not values or not values[-1].endswith("%"):
            continue
        shareholding.append({
            "label": label,
            "pct": values[-1],
            "color": SHAREHOLDING_COLORS.get(label, "#D8DAE3"),
        })

    return {
        "symbol": symbol.upper(),
        "header": raw["header"],
        "plRows": plRows,
        "balanceSheet": balanceSheet,
        "cashFlow": cashFlow,
        "quarters": quarters,
        "ratios": ratios,
        "shareholding": shareholding,
    }


def _fetch_price_series(company_id, days):
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    url = CHART_API_URL.format(company_id=company_id, days=days)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    price_dataset = next((d for d in data.get("datasets", []) if d.get("metric") == "Price"), None)
    if not price_dataset or not price_dataset.get("values"):
        raise RuntimeError("screener.in chart API returned no price data")

    return [(date, float(price)) for date, price in price_dataset["values"]]


def _fetch_price_history(symbol):
    raw = _get_raw(symbol)
    company_id = raw.get("company_id")
    if not company_id:
        raise RuntimeError(f"no screener.in company id found for {symbol!r}")

    periods = {}
    for label, days in CHART_PERIODS:
        series = _fetch_price_series(company_id, days)
        if len(series) < 2:
            continue
        prices = [p for _, p in series]
        periods[label] = {
            "points": sparkline_points(prices, width=800, height=180),
            "startDate": series[0][0],
            "endDate": series[-1][0],
            "startPrice": prices[0],
            "endPrice": prices[-1],
        }

    if not periods:
        raise RuntimeError(f"not enough price history to chart for {symbol!r}")

    return {"periods": periods}


def get_price_history(symbol):
    """Real daily-close price history from screener.in, one request per
    period tab (see CHART_API_URL comment for why), cached together."""
    key = f"screener_prices_{symbol.upper()}"
    return cache.get_or_fetch(key, PRICE_CACHE_TTL_SECONDS, lambda: _fetch_price_history(symbol))
