"""News connector — pulls market/business headlines from public RSS feeds.

Summaries + links only (no full-article scraping), matching the low-legal
-risk approach chosen in the Quantile architecture doc. Gainers/losers are
NOT produced here — those need a live quotes feed (Dhan), out of scope for
a news connector — callers should merge in mock_data's gainers/losers (or
a future quotes connector) themselves.
"""

import datetime
import re

import feedparser

from connectors import cache
from connectors.format_utils import TAG_PALETTE, THUMB_COLORS, time_ago

FEEDS = [
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "source": "Economic Times"},
    {"url": "https://www.moneycontrol.com/rss/marketreports.xml", "source": "Moneycontrol"},
    {"url": "https://www.livemint.com/rss/markets", "source": "Livemint"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss", "source": "Business Standard"},
]

TAG_KEYWORDS = [
    ("IPO", re.compile(r"\bipo\b|\bgmp\b|grey market|listing day", re.I)),
    ("ECONOMY", re.compile(r"\brbi\b|repo rate|inflation|\bgdp\b|fiscal|monetary policy", re.I)),
    ("GLOBAL", re.compile(r"\bfed\b|federal reserve|wall street|\bus\b|china|global markets", re.I)),
    ("CORPORATE", re.compile(r"profit|results|q[1-4] |buyback|board|earnings|acquisition|merger", re.I)),
]

CACHE_KEY = "news_data"
CACHE_TTL_SECONDS = 15 * 60
MAX_STORIES = 12
MAX_TRENDING = 5


def _infer_tag(title):
    for tag, pattern in TAG_KEYWORDS:
        if pattern.search(title):
            return tag
    return "MARKETS"


def _entry_published(entry):
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            return datetime.datetime(*value[:6])
    return None


def _fetch_feed(feed):
    parsed = feedparser.parse(feed["url"])
    entries = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "").strip()
        if not title:
            continue
        entries.append({
            "title": title,
            "published": _entry_published(entry),
            "source": feed["source"],
        })
    return entries


def _fetch_all():
    all_entries = []
    for feed in FEEDS:
        try:
            all_entries.extend(_fetch_feed(feed))
        except Exception:
            continue

    all_entries.sort(key=lambda e: e["published"] or datetime.datetime.min, reverse=True)

    stories = []
    for i, entry in enumerate(all_entries[:MAX_STORIES]):
        tag = _infer_tag(entry["title"])
        palette = TAG_PALETTE[tag]
        stories.append({
            "tag": tag,
            "tagColor": palette["tagColor"],
            "tagBg": palette["tagBg"],
            "time": time_ago(entry["published"]),
            "headline": entry["title"],
            "source": entry["source"],
            "thumbBg": THUMB_COLORS[i % len(THUMB_COLORS)],
        })

    trending = [
        {"rank": f"{i + 1:02d}", "headline": entry["title"]}
        for i, entry in enumerate(all_entries[:MAX_TRENDING])
    ]

    if not stories:
        raise RuntimeError("No RSS feeds returned any entries")

    return {"stories": stories, "trending": trending}


def get_news_data():
    return cache.get_or_fetch(CACHE_KEY, CACHE_TTL_SECONDS, _fetch_all)
