"""News connector — market/stock headlines plus company order wins.

Summaries + links only (no full-article scraping), matching the low-legal
-risk approach chosen in the Quantile architecture doc. Three kinds of
source, each fetched and cached independently so one being down never
takes the others with it:

  1. Publisher RSS feeds (ET, Livemint, Business Standard, BusinessLine,
     NDTV Profit) — general market and company news.
  2. A Google News RSS search for order-win headlines ("X bags ₹500 crore
     order") — aggregates many smaller outlets that cover these first.
  3. Exchange filings — BSE's "Award of Order / Receipt of Order"
     announcements and NSE's "Bagging/Receiving of orders/contracts" —
     the official, fastest source for order wins, straight from the
     company. Both are fetched because each blocks some IPs: confirmed
     2026-09-25, BSE's API 403s the staging EC2 instance while NSE's
     works there (and both work from a home connection). The two are
     deduped per company per day.

Moneycontrol's feeds were dropped: every one of them returns 403 to
non-browser clients (confirmed 2026-09-25), so it contributed nothing.

Gainers/losers are NOT produced here — those need a live quotes feed
(Dhan); app.py's /api/news merges them in from the dashboard's cached
watchlist metrics.
"""

import datetime
import re
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

from connectors import cache
from connectors.format_utils import TAG_PALETTE, THUMB_COLORS

FEEDS = [
    {"url": "https://www.livemint.com/rss/markets", "source": "Livemint"},
    {"url": "https://www.livemint.com/rss/companies", "source": "Livemint"},
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "source": "Economic Times"},
    {"url": "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms", "source": "Economic Times"},
    {"url": "https://economictimes.indiatimes.com/markets/stocks/earnings/rssfeeds/2143429.cms", "source": "Economic Times"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss", "source": "Business Standard"},
    {"url": "https://www.business-standard.com/rss/companies-101.rss", "source": "Business Standard"},
    {"url": "https://www.thehindubusinessline.com/markets/feeder/default.rss", "source": "BusinessLine"},
    {"url": "https://www.thehindubusinessline.com/companies/feeder/default.rss", "source": "BusinessLine"},
    {"url": "https://feeds.feedburner.com/ndtvprofit-latest", "source": "NDTV Profit"},
]

ORDER_WIN_NEWS_FEED = (
    "https://news.google.com/rss/search?q=(bags+OR+secures+OR+wins+OR+receives+OR+bagged)"
    "+order+(crore+OR+cr+OR+contract)+when:2d&hl=en-IN&gl=IN&ceid=IN:en"
)

BSE_ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_ATTACHMENT_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{}"
BSE_ORDER_SUBCATEGORY = "Award of Order / Receipt of Order"
NSE_HOME_URL = "https://www.nseindia.com/"
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"
# NSE's "Action(s) taken or orders passed" is regulatory/court orders
# against a company, not an order win — only these two count.
NSE_ORDER_WIN_DESCS = {"bagging/receiving of orders/contracts", "awarding of order(s)/contract(s)"}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}
HTTP_TIMEOUT_SECONDS = 10
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Short TTLs — this is meant to feel close to live. Each source is its
# own cache entry, so a slow one only delays its own refresh.
FEED_CACHE_TTL_SECONDS = 3 * 60
FILINGS_CACHE_TTL_SECONDS = 2 * 60
FILINGS_LOOKBACK_DAYS = 3

MAX_STORIES = 80
MAX_ORDER_WINS = 40
MAX_TRENDING = 5

# A win verb followed closely by an order/contract noun, or the filing
# phrasings companies use. Deliberately needs both halves: "wins" or
# "order" alone matches far too much market commentary.
ORDER_WIN_RE = re.compile(
    r"\b(bag(s|ged|ging)?|secur(e|es|ed|ing)|win(s|ning)?|won|receiv(e|es|ed|ing)|grab(s|bed)?|land(s|ed)?|clinch(es|ed)?|awarded|bags)\b"
    r"[^.?!;:|]{0,80}?\b(orders?|contracts?|work orders?|loa|letter of (award|intent)|projects? worth)\b"
    r"|\border (win|wins|inflows?)\b"
    r"|\b(receipt|award) of (work )?orders?\b",
    re.I,
)
# ...but not a regulator/court/tax "order" someone received.
NOT_ORDER_WIN_RE = re.compile(r"\b(court|tribunal|nclt|nclat|sebi|rbi|gst|tax|penalt\w*|demand notice|show cause|attach\w*|stay)\b", re.I)

ORDER_VALUE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b|lakhs?|million|mn\b|billion|bn\b)"
    r"|([\d,]+(?:\.\d+)?)\s*(crores?|cr\b)",
    re.I,
)

TAG_KEYWORDS = [
    ("IPO", re.compile(r"\bipo\b|\bgmp\b|grey market|listing day", re.I)),
    ("ECONOMY", re.compile(r"\brbi\b|repo rate|inflation|\bgdp\b|fiscal|monetary policy", re.I)),
    ("GLOBAL", re.compile(r"\bfed\b|federal reserve|wall street|\bus\b|china|global markets", re.I)),
    ("CORPORATE", re.compile(r"profit|results|q[1-4] |buyback|board|earnings|acquisition|merger|stake", re.I)),
]


def is_order_win(title):
    return bool(ORDER_WIN_RE.search(title)) and not NOT_ORDER_WIN_RE.search(title)


def order_value(text):
    """'₹2,025 Cr' style string for the first order size in `text`, or None."""
    match = ORDER_VALUE_RE.search(text or "")
    if not match:
        return None
    number = (match.group(1) or match.group(3)).replace(",", "")
    unit = (match.group(2) or match.group(4)).lower()
    try:
        value = float(number)
    except ValueError:
        return None
    if unit.startswith("lakh"):
        value /= 100
    elif unit in ("million", "mn"):
        value /= 10  # ₹1 million = ₹0.1 crore
    elif unit in ("billion", "bn"):
        value *= 100
    if value <= 0:
        return None
    return f"₹{value:,.2f} Cr" if value < 10 else f"₹{value:,.0f} Cr"


def _infer_tag(title):
    if is_order_win(title):
        return "ORDER WIN"
    for tag, pattern in TAG_KEYWORDS:
        if pattern.search(title):
            return tag
    return "MARKETS"


def _iso_utc(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _entry_published(entry):
    # feedparser normalises *_parsed to UTC.
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            return datetime.datetime(*value[:6], tzinfo=datetime.timezone.utc)
    return None


def _parse_feed(url):
    # Fetched with requests (not feedparser.parse(url)) for a real timeout
    # and browser headers — several publishers 403 feedparser's default UA.
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def _fetch_feed(feed):
    items = []
    for entry in _parse_feed(feed["url"]).entries:
        title = getattr(entry, "title", "").strip()
        if not title:
            continue
        items.append({
            "headline": title,
            "link": getattr(entry, "link", None),
            "source": feed["source"],
            "publishedAt": _iso_utc(_entry_published(entry)),
        })
    return items


def _fetch_order_win_news():
    """Google News search results, kept only if the headline really reads
    as an order win (the search itself is loose)."""
    items = []
    for entry in _parse_feed(ORDER_WIN_NEWS_FEED).entries:
        title = getattr(entry, "title", "").strip()
        publisher = (getattr(entry, "source", None) or {}).get("title") or "Google News"
        # Google News appends " - Publisher" to every title.
        if title.endswith(f" - {publisher}"):
            title = title[: -len(f" - {publisher}")].strip()
        if not title or not is_order_win(title):
            continue
        items.append({
            "headline": title,
            "link": getattr(entry, "link", None),
            "source": publisher,
            "publishedAt": _iso_utc(_entry_published(entry)),
        })
    return items


def _ist_to_iso(text, fmt):
    try:
        return _iso_utc(datetime.datetime.strptime(text, fmt).replace(tzinfo=IST))
    except (TypeError, ValueError):
        return None


def _company_key(name):
    """Normalised company name so the same filing on BSE and NSE dedupes
    ('Steamhouse India Ltd' vs 'Steamhouse India Limited')."""
    name = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    return " ".join(w for w in name.split() if w not in ("ltd", "limited", "the"))


def _fetch_bse_order_filings():
    today = datetime.datetime.now(IST).date()
    start = today - datetime.timedelta(days=FILINGS_LOOKBACK_DAYS)
    resp = requests.get(
        BSE_ANNOUNCEMENTS_URL,
        params={
            "pageno": 1, "strCat": "Company Update", "subcategory": BSE_ORDER_SUBCATEGORY,
            "strPrevDate": start.strftime("%Y%m%d"), "strToDate": today.strftime("%Y%m%d"),
            "strScrip": "", "strSearch": "P", "strType": "C",
        },
        headers={**BROWSER_HEADERS, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    items = []
    for row in resp.json().get("Table", []):
        company = (row.get("SLONGNAME") or "").strip()
        headline = (row.get("HEADLINE") or row.get("NEWSSUB") or "").strip()
        attachment = row.get("ATTACHMENTNAME")
        items.append({
            "company": company,
            "companyKey": _company_key(company),
            "symbol": None,
            "headline": headline,
            "link": BSE_ATTACHMENT_URL.format(attachment) if attachment else None,
            "source": "BSE filing",
            "publishedAt": _ist_to_iso((row.get("NEWS_DT") or "")[:19], "%Y-%m-%dT%H:%M:%S"),
        })
    return items


def _fetch_nse_order_filings():
    today = datetime.datetime.now(IST).date()
    start = today - datetime.timedelta(days=FILINGS_LOOKBACK_DAYS)
    session = requests.Session()
    session.headers.update({**BROWSER_HEADERS, "Accept": "application/json", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
    session.get(NSE_HOME_URL, timeout=HTTP_TIMEOUT_SECONDS)  # sets the cookies the API requires
    resp = session.get(
        NSE_ANNOUNCEMENTS_URL,
        params={"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": today.strftime("%d-%m-%Y")},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    items = []
    for row in resp.json():
        if (row.get("desc") or "").strip().lower() not in NSE_ORDER_WIN_DESCS:
            continue
        company = (row.get("sm_name") or "").strip()
        text = (row.get("attchmntText") or "").strip()
        # "X Limited has informed the Exchange about Bagging/..." adds
        # nothing beyond the company name — say it plainly instead.
        headline = text if "has informed the exchange about" not in text.lower() else "Bagging/receiving of orders/contracts"
        items.append({
            "company": company,
            "companyKey": _company_key(company),
            "symbol": row.get("symbol"),
            "headline": headline,
            "link": row.get("attchmntFile"),
            "source": "NSE filing",
            "publishedAt": _ist_to_iso(row.get("an_dt"), "%d-%b-%Y %H:%M:%S"),
        })
    return items


def _cached(key, ttl, fetch_fn):
    """A failing source returns [] instead of raising, so the page still
    renders from the others (cache.get_or_fetch already serves stale data
    when a refresh fails, if there is any)."""
    try:
        return cache.get_or_fetch(key, ttl, fetch_fn) or []
    except Exception:
        return []


# Filing headlines that are pure boilerplate — the company name is
# already shown separately, so these carry no information themselves.
BOILERPLATE_FILING_RE = re.compile(r"^(pursuant to|please find|intimation|disclosure (of|under)|announcement under|reg(ulation)?\.? ?30)", re.I)


INFORMED_EXCHANGE_RE = re.compile(r"^.*?has informed the exchange (regarding|about)\s*[-–:]?\s*", re.I)


def _filing_headline(headline):
    headline = INFORMED_EXCHANGE_RE.sub("", headline or "").strip()
    if not headline or (BOILERPLATE_FILING_RE.search(headline) and not order_value(headline)):
        return "Order received — details in the filing"
    return headline


def _news_company_key(headline):
    """Rough company key for an order-win headline: the words before the
    win verb ("KPIL Bags Rs 2,025 Cr..." -> "kpil"). Used only to collapse
    several outlets covering the same order on the same day."""
    match = ORDER_WIN_RE.search(headline)
    prefix = headline[: match.start()] if match else headline
    return _company_key(prefix)[:40]


def _headline_key(headline):
    return re.sub(r"[^a-z0-9]", "", headline.lower())[:70]


def _newest_first(items):
    return sorted(items, key=lambda i: i.get("publishedAt") or "", reverse=True)


def _fetch_all():
    jobs = {f"news_feed_{i}": (FEED_CACHE_TTL_SECONDS, lambda f=feed: _fetch_feed(f)) for i, feed in enumerate(FEEDS)}
    jobs["news_order_win_search"] = (FEED_CACHE_TTL_SECONDS, _fetch_order_win_news)
    jobs["news_bse_order_filings"] = (FILINGS_CACHE_TTL_SECONDS, _fetch_bse_order_filings)
    jobs["news_nse_order_filings"] = (FILINGS_CACHE_TTL_SECONDS, _fetch_nse_order_filings)
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {key: pool.submit(_cached, key, ttl, fn) for key, (ttl, fn) in jobs.items()}
        results = {key: f.result() for key, f in futures.items()}

    articles = []
    seen = set()
    for item in _newest_first([i for k, v in results.items() if k.startswith("news_feed_") or k == "news_order_win_search" for i in v]):
        key = _headline_key(item["headline"])
        if key in seen:
            continue  # same story syndicated across feeds
        seen.add(key)
        articles.append(item)

    # Filings: BSE first, so a company that filed on both exchanges keeps
    # BSE's (usually more descriptive) headline and gains NSE's symbol.
    filings = {}
    for item in _newest_first(results["news_bse_order_filings"]) + _newest_first(results["news_nse_order_filings"]):
        key = (item["companyKey"], (item["publishedAt"] or "")[:10])
        if key in filings:
            filings[key]["symbol"] = filings[key]["symbol"] or item["symbol"]
            continue
        filings[key] = dict(item)

    order_wins = [
        {"kind": "filing", "company": f["company"], "symbol": f["symbol"], "headline": _filing_headline(f["headline"]), "link": f["link"],
         "source": f["source"], "publishedAt": f["publishedAt"], "orderValue": order_value(f["headline"])}
        for f in filings.values()
    ]
    # News: one per order per day — the same order is usually covered by
    # several outlets within hours, under different wordings ("KPIL Bags
    # Rs 2,025 Cr..." / "KPIL Announces New Order Wins of Rs 2,025 Crores"),
    # so either the same company prefix or the same order value on the
    # same day counts as a repeat. articles is newest-first, so the
    # first-seen (latest) report is kept.
    seen_news = set()
    for a in articles:
        if not is_order_win(a["headline"]):
            continue
        day = (a["publishedAt"] or "")[:10]
        value = order_value(a["headline"])
        keys = {k for k in (("company", _news_company_key(a["headline"]), day), ("value", value, day)) if k[1]}
        if keys & seen_news:
            continue
        seen_news |= keys
        order_wins.append({"kind": "news", "company": None, "symbol": None, "headline": a["headline"], "link": a["link"],
                           "source": a["source"], "publishedAt": a["publishedAt"], "orderValue": value})
    order_wins = _newest_first(order_wins)[:MAX_ORDER_WINS]

    stories = []
    for i, article in enumerate(articles[:MAX_STORIES]):
        tag = _infer_tag(article["headline"])
        stories.append({
            **article,
            "tag": tag,
            **TAG_PALETTE[tag],
            "thumbBg": THUMB_COLORS[i % len(THUMB_COLORS)],
            "orderValue": order_value(article["headline"]) if tag == "ORDER WIN" else None,
        })

    if not stories and not order_wins:
        raise RuntimeError("No news source returned any entries")

    return {
        "stories": stories,
        "orderWins": order_wins,
        "trending": [{"rank": f"{i + 1:02d}", "headline": a["headline"], "link": a["link"]} for i, a in enumerate(articles[:MAX_TRENDING])],
        "updatedAt": _iso_utc(datetime.datetime.now(datetime.timezone.utc)),
    }


def get_news_data():
    # No outer cache: each source above is already cached on its own
    # short TTL, and merging them is cheap.
    return _fetch_all()


# ---------------------------------------------------------------------
# Per-stock filings for the Research page
# ---------------------------------------------------------------------
STOCK_FILINGS_DAYS = 30
STOCK_FILINGS_CACHE_TTL_SECONDS = 30 * 60
STOCK_FILINGS_MAX = 10


def _fetch_nse_stock_filings(symbol):
    today = datetime.datetime.now(IST).date()
    start = today - datetime.timedelta(days=STOCK_FILINGS_DAYS)
    session = requests.Session()
    session.headers.update({**BROWSER_HEADERS, "Accept": "application/json", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
    session.get(NSE_HOME_URL, timeout=HTTP_TIMEOUT_SECONDS)
    resp = session.get(
        NSE_ANNOUNCEMENTS_URL,
        params={"index": "equities", "symbol": symbol, "from_date": start.strftime("%d-%m-%Y"), "to_date": today.strftime("%d-%m-%Y")},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    items = []
    for row in resp.json():
        desc = (row.get("desc") or "").strip()
        text = (row.get("attchmntText") or "").strip()
        # "X Limited has informed the Exchange about/regarding ..." — keep
        # just what it's about.
        detail = re.sub(r"^.*?has informed the exchange (?:about|regarding)\s*[-–:]?\s*", "", text, flags=re.I).strip()
        items.append({
            "category": desc,
            "detail": detail if detail and detail.lower() != desc.lower() else "",
            "link": row.get("attchmntFile"),
            "publishedAt": _ist_to_iso(row.get("an_dt"), "%d-%b-%Y %H:%M:%S"),
            "orderWin": desc.lower() in NSE_ORDER_WIN_DESCS or is_order_win(text),
        })
    return _newest_first(items)


def _company_core(name):
    """'Tata Steel Ltd' -> 'tata steel'; used to match order-win headlines
    that name the company rather than its ticker."""
    return _company_key(re.sub(r"\b(india|industries|enterprises|corporation|company|co)\b", "", (name or "").lower()))


def get_stock_filings(symbol, company_name=None):
    """{filings, orderWinNews, source} for one stock: its last
    STOCK_FILINGS_DAYS days of NSE announcements (order wins flagged),
    plus any order-win news from the News page's feeds naming it.
    filings is None if NSE couldn't be reached (the page then falls back
    to screener's BSE announcements)."""
    symbol = symbol.strip().upper()
    try:
        filings = cache.get_or_fetch(f"nse_stock_filings_{symbol}", STOCK_FILINGS_CACHE_TTL_SECONDS, lambda: _fetch_nse_stock_filings(symbol))[:STOCK_FILINGS_MAX]
    except Exception:
        filings = None

    core = _company_core(company_name)
    news = []
    try:
        for w in get_news_data().get("orderWins", []):
            if w.get("kind") != "news":
                continue  # filings already come from NSE above
            headline = w.get("headline") or ""
            if re.search(rf"\b{re.escape(symbol)}\b", headline, re.I) or (len(core) >= 4 and core in _company_key(headline)):
                news.append(w)
    except Exception:
        pass
    return {"filings": filings, "orderWinNews": news[:5]}
