"""Results Scanner — quarterly-results screens (QoQ / YoY growth) over the
stock list in s3://new-dhan-trading-data/marketsmith-data/input/
raw_mapping_all_symbols.csv, shown as entries in the existing Scanner page.

Data source: each company's public screener.in page (/company/SYMBOL/),
the same pages connectors/fundamentals_connector.py already reads.
Trendlyne's Rapid Results page is disallowed for all bots in its
robots.txt, and screener.in's robots.txt disallows paginating its query
screens (?page=), so neither is used — see docs/results-scanner.md.

Two parts:
  * refresh_store() — the slow, polite fetcher (one request every
    MIN_REQUEST_INTERVAL_SECONDS, retry + backoff, robots.txt checked)
    that keeps a disk store of each company's last quarters. A company
    already showing the target quarter isn't re-fetched for it, so after
    the first full pass each day's pass only covers who hasn't reported.
  * scan(criteria, quarter) — pure: metrics, flags and nested AND/OR
    criteria over the store. No network.

New data sources plug in through SOURCES: anything with fetch(symbol)
-> quarters dict (see ScreenerCompanyPages.fetch).
"""

import datetime
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

from connectors import cache

logger = logging.getLogger(__name__)

UNIVERSE_BUCKET = "new-dhan-trading-data"
UNIVERSE_KEY = "marketsmith-data/input/raw_mapping_all_symbols.csv"
AWS_REGION = "ap-south-1"

USER_AGENT = "Mozilla/5.0 (compatible; QuantileResultsScanner/1.0; +https://dz1fb1xrtg7b3.cloudfront.net)"
MIN_REQUEST_INTERVAL_SECONDS = float(os.environ.get("RESULTS_SCANNER_REQUEST_INTERVAL", "2"))
MAX_ATTEMPTS = 3
SCAN_CACHE_TTL_SECONDS = int(os.environ.get("RESULTS_SCANNER_CACHE_TTL", str(15 * 60)))
# A company that already shows the target quarter is re-checked only this
# often (for restatements); one that hasn't reported yet, once a day.
REPORTED_RECHECK_DAYS = 7
PENDING_RECHECK_HOURS = 20

STORE_PATH = os.path.join(cache.CACHE_DIR, "results_scanner_store.json")

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
QUARTER_HEADER = re.compile(r"^([A-Z][a-z]{2}) (\d{4})$")

# Screener labels the same lines differently for banks/NBFCs.
ROW_ALIASES = {
    "sales": ("Sales", "Revenue"),
    "ebitda": ("Operating Profit", "Financing Profit"),
    "opm": ("OPM %", "Financing Margin %"),
    "net_profit": ("Net Profit",),
    "eps": ("EPS in Rs",),
}

FINANCIAL_WORDS = re.compile(r"\b(bank|banks|finance|financial|finserv|nbfc|insurance|assurance|amc|asset management|capital markets|housing finance|lending|credit)\b", re.I)

# ------------------------------------------------------------------ parsing


def to_number(text):
    """'1,192.67' -> 1192.67, '12%' -> 12.0, '—' / '-' / '' -> None."""
    if text is None:
        return None
    text = str(text).strip().replace(",", "").replace("%", "").replace("₹", "")
    if text in ("", "-", "—", "–", "NA", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def quarter_key(label):
    """'Sep 2026' -> '2026-09' (sortable), else None."""
    m = QUARTER_HEADER.match(label or "")
    return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}" if m and m.group(1) in MONTHS else None


def shift_quarter(key, quarters):
    year, month = int(key[:4]), int(key[5:])
    total = year * 12 + (month - 1) - 3 * quarters
    return f"{total // 12}-{total % 12 + 1:02d}"


def quarter_label(key):
    """'2026-09' -> "Sep '26"."""
    name = [m for m, i in MONTHS.items() if i == int(key[5:])][0]
    return f"{name} '{key[2:4]}"


def parse_company_page(html):
    """screener.in company page -> {"quarters": {"2026-09": {sales, ebitda,
    opm, net_profit, eps}}, "industry": [...], "name": str}. Quarters
    with no usable header are skipped."""
    soup = BeautifulSoup(html, "lxml")
    section = soup.find("section", id="quarters")
    table = section.find("table") if section else None
    quarters = {}
    if table is not None:
        headers = [th.get_text(strip=True) for th in table.find_all("th")][1:]
        rows = {}
        for tr in (table.find("tbody") or table).find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells:
                rows[cells[0].get_text(strip=True).rstrip("+").strip()] = [c.get_text(strip=True) for c in cells[1:]]
        for i, header in enumerate(headers):
            key = quarter_key(header)
            if not key:
                continue
            record = {}
            for field, labels in ROW_ALIASES.items():
                values = next((rows[l] for l in labels if l in rows), [])
                record[field] = to_number(values[i]) if i < len(values) else None
            # screener prints OPM rounded to whole % (19% -> 20% reads as
            # +5.3% when it's really +3.6%); recompute it unrounded.
            if record["ebitda"] is not None and record["sales"]:
                record["opm"] = record["ebitda"] / record["sales"] * 100
            quarters[key] = record

    industry = []
    peers = soup.find("section", id="peers")
    if peers is not None:
        for a in peers.select("p.sub a"):
            if a.get("title") in ("Broad Sector", "Sector", "Broad Industry", "Industry"):
                industry.append(a.get_text(strip=True))
    h1 = soup.find("h1")
    return {"quarters": quarters, "industry": industry, "name": h1.get_text(strip=True) if h1 else ""}


# ------------------------------------------------------------ data source


class RateLimiter:
    """At most one request per `interval` seconds across all threads."""

    def __init__(self, interval):
        self.interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            delay = self._last + self.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class ScreenerCompanyPages:
    """fetch(symbol) -> parsed page dict (see parse_company_page)."""

    name = "screener"
    base = "https://www.screener.in"

    def __init__(self, session=None, limiter=None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.limiter = limiter or RateLimiter(MIN_REQUEST_INTERVAL_SECONDS)
        self._robots = None

    def allowed(self, url):
        if self._robots is None:
            robots = urllib.robotparser.RobotFileParser(self.base + "/robots.txt")
            self.limiter.wait()
            try:
                resp = self.session.get(self.base + "/robots.txt", timeout=15)
                robots.parse(resp.text.splitlines())
            except requests.RequestException:
                robots.parse(["User-agent: *", "Disallow: /"])  # unknown -> don't fetch
            self._robots = robots
        return self._robots.can_fetch(USER_AGENT, url)

    def _get(self, url):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.limiter.wait()
            status = None
            try:
                resp = self.session.get(url, timeout=20)
                status = resp.status_code
                if status == 200:
                    return resp.text
                if status == 404:
                    return None
            except requests.RequestException as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                logger.info("retry %s after %s", url, exc)
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{url} -> HTTP {status}")
            # Backoff on top of the rate limit — longer when told to slow down.
            time.sleep(2 ** attempt * (5 if status == 429 else 1))
        return None

    def fetch(self, symbol):
        # Consolidated first; a company with no subsidiaries serves an
        # empty consolidated table, so fall back to standalone.
        for path in (f"/company/{symbol}/consolidated/", f"/company/{symbol}/"):
            html = self._get(self.base + path)
            if html:
                parsed = parse_company_page(html)
                if parsed["quarters"]:
                    parsed["basis"] = "consolidated" if "consolidated" in path else "standalone"
                    return parsed
        return None


SOURCES = {"screener": ScreenerCompanyPages}

# ------------------------------------------------------------------ store

_store_lock = threading.Lock()


def load_store(path=None):
    path = path or STORE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_store(store, path=None):
    path = path or STORE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(store, fh)
    os.replace(path + ".tmp", path)


def load_universe():
    """[(symbol, market_cap_cr or None)] from the S3 stock list."""
    import boto3
    import pandas as pd
    obj = boto3.client("s3", region_name=AWS_REGION).get_object(Bucket=UNIVERSE_BUCKET, Key=UNIVERSE_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df = df.dropna(subset=["Stock Name"])
    out = []
    for _, r in df.iterrows():
        cap = r.get("Market Cap")
        out.append((str(r["Stock Name"]).strip().upper(), float(cap) if cap == cap and cap is not None else None))
    return out


def expected_quarter(today=None):
    """Latest calendar quarter that has ended: Oct 25 -> '2026-09'."""
    today = today or datetime.date.today()
    month = ((today.month - 1) // 3) * 3  # 0, 3, 6, 9
    if month == 0:
        return f"{today.year - 1}-12"
    return f"{today.year}-{month:02d}"


def needs_fetch(entry, target, now):
    if not entry:
        return True
    age_h = (now - entry.get("fetched_at", 0)) / 3600
    if target in entry.get("quarters", {}):
        return age_h >= REPORTED_RECHECK_DAYS * 24
    return age_h >= PENDING_RECHECK_HOURS


def refresh_store(source=None, universe=None, stop=None, max_symbols=None):
    """One polite pass over the universe. Returns counts."""
    source = source or ScreenerCompanyPages()
    universe = universe if universe is not None else load_universe()
    target = expected_quarter()
    store = load_store()
    started, fetched, failed = time.time(), 0, 0
    for symbol, cap in universe:
        if stop is not None and stop():
            break
        if max_symbols is not None and fetched >= max_symbols:
            break
        entry = store.get(symbol)
        if not needs_fetch(entry, target, time.time()):
            continue
        try:
            parsed = source.fetch(symbol)
        except Exception as exc:
            failed += 1
            logger.warning("results-scanner: %s failed - %s", symbol, exc)
            continue
        fetched += 1
        if parsed is None:
            store[symbol] = {"fetched_at": time.time(), "quarters": {}, "missing": True}
            continue
        first_seen = dict((entry or {}).get("first_seen", {}))
        for q in parsed["quarters"]:
            first_seen.setdefault(q, datetime.date.today().isoformat())
        store[symbol] = {**parsed, "market_cap": cap, "fetched_at": time.time(), "first_seen": first_seen}
        if fetched % 25 == 0:
            with _store_lock:
                save_store(store)
    with _store_lock:
        save_store(store)
    result = {"fetched": fetched, "failed": failed, "seconds": round(time.time() - started), "companies": len(store), "target": target}
    logger.info("results-scanner refresh: %s", result)
    print(f"[results-scanner] refresh {result}", flush=True)
    return result


# ---------------------------------------------------------------- metrics


def pct(now, base, negative_base=False):
    """% change; None if either side is missing or the base is <= 0 —
    unless negative_base, which measures off |base| (a loss shrinking or
    turning into profit reads as a gain). A zero base is always None."""
    if now is None or base is None or base == 0:
        return None
    if base < 0:
        return (now - base) / abs(base) * 100 if negative_base else None
    return (now / base - 1) * 100


def _pct(now, base, negative_base=False):
    return pct(now, base, negative_base)


def company_metrics(entry, quarter, negative_base=False):
    """Row of QoQ/YoY metrics for `quarter` ('2026-09'), or None if the
    company hasn't reported it."""
    quarters = entry.get("quarters", {})
    cur = quarters.get(quarter)
    if not cur or cur.get("sales") is None and cur.get("net_profit") is None:
        return None
    prev = quarters.get(shift_quarter(quarter, 1), {})
    ago = quarters.get(shift_quarter(quarter, 4), {})

    def pct(now, base):
        return _pct(now, base, negative_base)

    m = {
        "sales_qoq": pct(cur.get("sales"), prev.get("sales")),
        "ebitda_qoq": pct(cur.get("ebitda"), prev.get("ebitda")),
        "opm_qoq": pct(cur.get("opm"), prev.get("opm")),  # relative, not points
        "profit_qoq": pct(cur.get("net_profit"), prev.get("net_profit")),
        "eps_qoq": pct(cur.get("eps"), prev.get("eps")),
        "sales_yoy": pct(cur.get("sales"), ago.get("sales")),
        "ebitda_yoy": pct(cur.get("ebitda"), ago.get("ebitda")),
        "profit_yoy": pct(cur.get("net_profit"), ago.get("net_profit")),
        "eps_yoy": pct(cur.get("eps"), ago.get("eps")),
        "sales": cur.get("sales"),
        "net_profit": cur.get("net_profit"),
        "market_cap": entry.get("market_cap"),
    }
    return m


def is_financial(symbol, entry):
    text = " ".join([symbol, entry.get("name", ""), *entry.get("industry", [])])
    return bool(FINANCIAL_WORDS.search(text))


def flags_for(symbol, entry, metrics, quarter):
    flags = []
    if is_financial(symbol, entry):
        flags.append("financial")
    cur = entry["quarters"].get(quarter, {})
    prev = entry["quarters"].get(shift_quarter(quarter, 1), {})
    np_now, np_prev = cur.get("net_profit"), prev.get("net_profit")
    if np_now is not None and np_prev is not None and np_now > 0 and np_prev < 0.05 * np_now:
        flags.append("small_base")
    if metrics.get("profit_yoy") is not None and metrics["profit_yoy"] < 0:
        flags.append("yoy_decline")
    if any((metrics.get(k) or 0) > 300 for k in ("sales_qoq", "ebitda_qoq", "opm_qoq", "profit_qoq", "eps_qoq")):
        flags.append("extreme_move")
    return flags


FLAG_TEXT = {
    "financial": "Financial — EBITDA/OPM not meaningful, judge on NII, NIM, NPA",
    "small_base": "Weak base — QoQ jump off a weak base, check 4-5 quarter trend",
    "yoy_decline": "Profit down YoY",
    "extreme_move": "Extreme QoQ move (>300%) — check for one-offs",
}

# --------------------------------------------------------------- criteria

FIELDS = {
    "sales_qoq": "Sales QoQ %", "ebitda_qoq": "EBITDA QoQ %", "opm_qoq": "OPM QoQ %",
    "profit_qoq": "Profit QoQ %", "eps_qoq": "EPS QoQ %",
    "sales_yoy": "Sales YoY %", "ebitda_yoy": "EBITDA YoY %", "profit_yoy": "Profit YoY %", "eps_yoy": "EPS YoY %",
    "sales": "Sales (cr)", "net_profit": "Net profit (cr)", "market_cap": "Market cap (cr)",
}


def _rule_passes(rule, metrics):
    value = metrics.get(rule["field"])
    if value is None:
        return False  # missing / non-meaningful base fails every numeric condition
    op, target = rule["operator"], rule["value"]
    if op == ">":
        return value > target
    if op == ">=":
        return value >= target
    if op == "<":
        return value < target
    if op == "<=":
        return value <= target
    if op == "between":
        low, high = target
        return low <= value <= high
    raise ValueError(f"unknown operator {op!r}")


def evaluate(criteria, metrics):
    """criteria: {"op": "AND"|"OR", "rules": [rule | group]}."""
    results = (evaluate(r, metrics) if "rules" in r else _rule_passes(r, metrics) for r in criteria["rules"])
    return all(results) if criteria.get("op", "AND").upper() == "AND" else any(results)


def leaf_rules(criteria):
    for r in criteria["rules"]:
        if "rules" in r:
            yield from leaf_rules(r)
        else:
            yield r


def rule_text(rule):
    value = rule["value"]
    value = f"{value[0]}–{value[1]}" if rule["operator"] == "between" else f"{value:g}"
    return f"{FIELDS.get(rule['field'], rule['field'])} {rule['operator']} {value}"


def _rules(*items):
    return [{"field": f, "operator": ">", "value": v} for f, v in items]


QOQ_MOMENTUM = _rules(("sales_qoq", 2.6), ("profit_qoq", 8), ("ebitda_qoq", 5), ("opm_qoq", 2), ("eps_qoq", 6))
PRESETS = {
    "qoq_momentum": {"name": "QoQ Momentum", "criteria": {"op": "AND", "rules": QOQ_MOMENTUM}},
    "qoq_10_10": {"name": "QoQ 10/10", "criteria": {"op": "AND", "rules": _rules(("sales_qoq", 10), ("profit_qoq", 10))}},
    "qoq_yoy_strong": {"name": "QoQ + YoY strong", "criteria": {"op": "AND", "rules": QOQ_MOMENTUM + _rules(("profit_yoy", 0))}},
}


# Which absolute figures a rule's % compares: (quarter value key, quarters
# back for the base — 1 = previous quarter, 4 = year ago, 0 = no base).
FIELD_BASE = {
    "sales_qoq": ("sales", 1), "ebitda_qoq": ("ebitda", 1), "opm_qoq": ("opm", 1),
    "profit_qoq": ("net_profit", 1), "eps_qoq": ("eps", 1),
    "sales_yoy": ("sales", 4), "ebitda_yoy": ("ebitda", 4), "profit_yoy": ("net_profit", 4), "eps_yoy": ("eps", 4),
    "sales": ("sales", 0), "net_profit": ("net_profit", 0), "market_cap": (None, 0),
}


def _r2(v):
    return round(v, 2) if isinstance(v, float) else v


def report_card(entry, metrics, quarter, criteria):
    """Every condition checked for one company: figures, % and pass/fail.
    `excluded` when a condition's % isn't comparable (base <= 0 / missing)."""
    quarters = entry.get("quarters", {})
    checks = []
    for rule in leaf_rules(criteria):
        key, back = FIELD_BASE.get(rule["field"], (None, 0))
        now = quarters.get(quarter, {}).get(key) if key else None
        base = quarters.get(shift_quarter(quarter, back), {}).get(key) if key and back else None
        actual = metrics.get(rule["field"])
        checks.append({"field": rule["field"], "label": FIELDS[rule["field"]], "operator": rule["operator"], "value": rule["value"],
                       "now": _r2(now), "base": _r2(base), "actual": _r2(actual), "pass": _rule_passes(rule, metrics)})
    return {"checks": checks, "passed": sum(c["pass"] for c in checks), "total": len(checks),
            "excluded": any(c["actual"] is None for c in checks)}


def scan(criteria, quarter=None, store=None, exclude_financials=False, exclude_negative_base=True, min_market_cap=None):
    """-> {rows, reported, total_reported, matched, quarter, eliminated_most}.
    Pure over the store. rows: matches, by Profit QoQ best first. reported:
    every company that reported the quarter (after the filters), with its
    report card — for the page's stock lookup and report-cards view."""
    store = store if store is not None else load_store()
    quarter = quarter or expected_quarter()
    rows, reported, misses, cards = [], 0, {}, []
    for symbol, entry in store.items():
        metrics = company_metrics(entry, quarter, negative_base=not exclude_negative_base)
        if metrics is None:
            continue
        flags = flags_for(symbol, entry, metrics, quarter)
        if exclude_financials and "financial" in flags:
            continue
        if min_market_cap and (metrics.get("market_cap") or 0) < min_market_cap:
            continue
        reported += 1
        for rule in leaf_rules(criteria):
            if not _rule_passes(rule, metrics):
                text = rule_text(rule)
                misses[text] = (misses.get(text, (0, rule))[0] + 1, rule)
        matched = evaluate(criteria, metrics)
        head = {"symbol": symbol, "name": entry.get("name", ""), "reported": entry.get("first_seen", {}).get(quarter), "flags": flags}
        if matched:
            rows.append({**head, "basis": entry.get("basis"), **metrics})
        cards.append({**head, "matched": matched, "profit_qoq": _r2(metrics.get("profit_qoq")), "profit_yoy": _r2(metrics.get("profit_yoy")),
                      **report_card(entry, metrics, quarter, criteria)})
    rows.sort(key=lambda r: -(r["profit_qoq"] if r["profit_qoq"] is not None else -1e9))
    # Report cards: most conditions passed first, then profit QoQ; the
    # not-comparable ones last.
    cards.sort(key=lambda c: (c["excluded"], -c["passed"], -(c["profit_qoq"] if c["profit_qoq"] is not None else -1e9)))
    worst = max(misses.items(), key=lambda kv: kv[1][0]) if misses else None
    return {"rows": rows, "reported": cards, "total_reported": reported, "matched": len(rows), "quarter": quarter,
            "eliminated_most": {"rule": worst[0], "count": worst[1][0], "condition": worst[1][1]} if worst else None}


OPERATORS = (">", ">=", "<", "<=", "between")
MAX_RULES = 25
MAX_DEPTH = 3


class CriteriaError(ValueError):
    pass


def validate_criteria(criteria, depth=1):
    """Raises CriteriaError unless `criteria` is a well-formed group of
    known fields/operators (bounded size, so a request can't be huge)."""
    if not isinstance(criteria, dict) or str(criteria.get("op", "")).upper() not in ("AND", "OR"):
        raise CriteriaError("Each group needs op AND or OR.")
    rules = criteria.get("rules")
    if not isinstance(rules, list) or not rules:
        raise CriteriaError("Each group needs at least one condition.")
    if depth > MAX_DEPTH:
        raise CriteriaError(f"Groups can be nested at most {MAX_DEPTH} deep.")
    if sum(1 for _ in leaf_rules(criteria)) > MAX_RULES:
        raise CriteriaError(f"At most {MAX_RULES} conditions.")
    for r in rules:
        if "rules" in r:
            validate_criteria(r, depth + 1)
            continue
        if r.get("field") not in FIELDS:
            raise CriteriaError(f"Unknown field {r.get('field')!r}.")
        if r.get("operator") not in OPERATORS:
            raise CriteriaError(f"Unknown operator {r.get('operator')!r}.")
        v = r.get("value")
        if r["operator"] == "between":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
                raise CriteriaError("between needs [low, high].")
        elif not isinstance(v, (int, float)) or isinstance(v, bool):
            raise CriteriaError(f"{FIELDS[r['field']]} needs a number.")


def _normalized(criteria):
    """Same criteria, canonical shape — so a preset sent back from the page
    compares equal to PRESETS regardless of key order or int/float."""
    return json.loads(json.dumps(criteria, sort_keys=True), parse_float=float, parse_int=float)


def is_preset(criteria):
    return any(_normalized(criteria) == _normalized(p["criteria"]) for p in PRESETS.values())


def store_meta(store=None):
    """Quarters available (with how many companies reported each) and when
    the store was last refreshed."""
    store = store if store is not None else load_store()
    counts = {}
    for entry in store.values():
        for q in entry.get("quarters", {}):
            counts[q] = counts.get(q, 0) + 1
    target = expected_quarter()
    keys = sorted({target, *counts}, reverse=True)[:4]
    fetched = max((e.get("fetched_at", 0) for e in store.values()), default=0)
    return {
        "quarters": [{"key": k, "label": quarter_label(k), "reported": counts.get(k, 0)} for k in keys],
        "fetched_at": datetime.datetime.fromtimestamp(fetched).isoformat() if fetched else None,
        "companies": len(store),
    }


def cached_scan_criteria(criteria, quarter, **filters):
    """scan() cached SCAN_CACHE_TTL_SECONDS per source, quarter, criteria
    and filters. Returns (result, cached)."""
    key = f"results_scan_screener_{quarter}_{criteria_hash({'c': criteria, 'f': filters})}"
    hit = cache.peek(key)
    fresh = hit is not None and time.time() - hit["cached_at"] < SCAN_CACHE_TTL_SECONDS
    started = time.time()
    result = cache.get_or_fetch(key, SCAN_CACHE_TTL_SECONDS, lambda: scan(criteria, quarter, **filters))
    logger.info("results-scanner %s: %s of %s in %.2fs (cached=%s)", quarter, result["matched"], result["total_reported"], time.time() - started, fresh)
    return result, fresh


def criteria_hash(criteria):
    return hashlib.sha1(json.dumps(criteria, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------- refresher

REFRESH_START = datetime.time(9, 5)
REFRESH_END = datetime.time(10, 55)


def start_refresher(now_fn, enabled=True):
    """Daemon thread: one refresh pass a day inside the backend's morning
    window (it only runs 09:00-11:00 IST), stopping at REFRESH_END and
    resuming where it left off the next day."""
    if not enabled:
        return

    def loop():
        last_day = None
        while True:
            now = now_fn()
            if now.weekday() < 5 and REFRESH_START <= now.time() < REFRESH_END and last_day != now.date():
                last_day = now.date()
                try:
                    refresh_store(stop=lambda: now_fn().time() >= REFRESH_END)
                except Exception as exc:
                    print(f"[results-scanner] refresh failed: {exc}", flush=True)
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="results-scanner-refresh").start()
