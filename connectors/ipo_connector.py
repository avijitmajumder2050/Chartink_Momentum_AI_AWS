"""IPO/GMP connector.

investorgain.com's live GMP report (https://www.investorgain.com/report/ipo-gmp-live/331/)
is a Next.js app — the server response ships an empty <table id="reportTable">
that JS fills in after load via client-side fetch. Verified with `requests`
(gets nothing) vs Playwright (gets the full rendered table) while building
this connector. Same is true of chittorgarh.com's IPO list.

investorgain's single report already carries name, segment, price band, lot
size, GMP and the overall subscription multiple for every live/upcoming IPO
in one place, so this connector renders only that one page with a headless
Chromium (Playwright) rather than also merging chittorgarh's list — simpler,
one browser render per cache refresh instead of two, same data coverage for
what the IPO Hub page actually displays.

Not covered (would need a per-IPO detail page, out of scope for the list
view): category-wise QIB/NII/Retail/Employee subscription breakdown — the
`subCategories` block still comes from mock_data as a static placeholder.
"""

import datetime
import re

from playwright.sync_api import sync_playwright

from connectors import cache
from connectors.format_utils import THUMB_COLORS

REPORT_URL = "https://www.investorgain.com/report/ipo-gmp-live/331/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

STATUS_TAG = {
    "O": {"tag": "Open", "tagBg": "#E6F7F1", "tagColor": "#17A673"},
    "U": {"tag": "Upcoming", "tagBg": "#FBF2E1", "tagColor": "#B98A2E"},
    "C": {"tag": "Closed", "tagBg": "#F0F1F4", "tagColor": "#5B6270"},
}

SEGMENT_MAP = {
    "IPO": "Mainboard",
    "NSE SME": "SME",
    "BSE SME": "SME",
}

CACHE_KEY = "ipo_hub_data"
CACHE_TTL_SECONDS = 45 * 60


def _render_report_html():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(REPORT_URL, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_selector("#reportTable tbody tr", timeout=30000)
            page.wait_for_timeout(2000)  # let the table finish (re-)rendering after the first rows mount
            return page.content()
        finally:
            browser.close()


def _initials(name):
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "??"


def _parse_price_band(price_text):
    price_text = price_text.strip()
    if not price_text:
        return "TBA"
    nums = re.findall(r"[\d,]+(?:\.\d+)?", price_text)
    if len(nums) >= 2:
        return f"₹{nums[0]}–{nums[1]}"
    if nums:
        return f"₹{nums[0]}"
    return "TBA"


def _parse_gmp(gmp_text):
    """'₹ 68 (15.6%) 0 ↓ / 3 ↑' -> '+₹68 (15.6%)'; '₹ -- (-%) ...' -> 'GMP TBA'"""
    match = re.search(r"[₹]\s*(-{1,2}|\d[\d,]*)\s*\(([-\d.]+)%\)", gmp_text)
    if not match or match.group(1).strip("-") == "":
        return "GMP TBA"
    amount, pct = match.group(1), match.group(2)
    sign = "-" if amount.startswith("-") or pct.startswith("-") else "+"
    return f"{sign}₹{amount.lstrip('-')} ({pct.lstrip('-')}%)"


def _parse_sub(sub_text):
    sub_text = sub_text.strip()
    if not sub_text or sub_text == "-":
        return None
    match = re.search(r"[\d.]+", sub_text)
    return float(match.group()) if match else None


DATE_CELL = re.compile(r"(\d{1,2})-([A-Za-z]{3})")


def _reformat_date(cell_text):
    """Extracts just the leading 'DD-Mon' date from a cell that, for
    already-closed IPOs, has extra listing-gain tooltip text fused onto
    the end with no separator (e.g. '11-SepGMP: 1') -> '11 Sep'."""
    match = DATE_CELL.search(cell_text)
    return f"{match.group(1)} {match.group(2)}" if match else ""


def _parse_rows(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="reportTable")
    if table is None:
        raise RuntimeError("reportTable not found in rendered investorgain page")

    body_rows = table.find("tbody").find_all("tr")
    # Column count needed to reach the "Close" cell (index 8) below; the
    # <th> header group repeats itself (sticky-column duplication) with
    # inconsistent "▲▼" sort-arrow suffixes, so it's not a reliable way
    # to compute the real column count — checking the row's own cell
    # count is simpler and just as effective at skipping malformed rows.
    MIN_CELLS = 9

    ipos = []
    for i, row in enumerate(body_rows):
        cells = row.find_all("td")
        if len(cells) < MIN_CELLS:
            continue  # malformed/separator row, skip rather than crash the batch

        name_cell = cells[0]
        anchor = name_cell.find("a")
        # The segment/status spans are siblings of the name link, not
        # nested inside it, so the anchor's own text is already the
        # clean company name — no need to strip anything back out of it
        # (an earlier version did a blind str.replace of the status
        # letter, which corrupted names containing that letter, e.g.
        # "Prasol Chemicals" -> "Prasol hemicals" when status was "C").
        name = (anchor.get_text(" ", strip=True) if anchor else name_cell.get_text(" ", strip=True))
        spans = [s.get_text(strip=True) for s in name_cell.find_all(["span", "small"])]
        segment_label = spans[0] if spans else "IPO"
        status_code = spans[1] if len(spans) > 1 else "U"

        status = STATUS_TAG.get(status_code, STATUS_TAG["U"])
        close_date = _reformat_date(cells[8].get_text(strip=True))
        if status_code == "O" and close_date == datetime.date.today().strftime("%d %b").lstrip("0"):
            status = {**status, "tag": "Closing today"}

        sub_x = _parse_sub(cells[3].get_text(strip=True))
        sub_pct = "100%" if sub_x is not None and sub_x >= 1 else (f"{sub_x * 100:.0f}%" if sub_x is not None else "-")
        lot_text = cells[6].get_text(strip=True)

        ipos.append({
            "name": name,
            "segment": SEGMENT_MAP.get(segment_label, "Mainboard"),
            "initials": _initials(name),
            "logoBg": THUMB_COLORS[i % len(THUMB_COLORS)],
            "tag": status["tag"],
            "tagBg": status["tagBg"],
            "tagColor": status["tagColor"],
            "priceBand": _parse_price_band(cells[4].get_text(strip=True)),
            "lot": f"{lot_text} shares" if lot_text else "-",
            "gmp": _parse_gmp(cells[1].get_text(" ", strip=True)),
            "subLabel": f"{sub_x:.1f}x" if sub_x is not None else "-",
            "subPct": sub_pct,
            "closes": close_date,
        })

    if not ipos:
        raise RuntimeError("Parsed 0 IPO rows from investorgain report")

    return ipos


def _fetch_all():
    import mock_data

    html = _render_report_html()
    ipos = _parse_rows(html)
    return {
        "ipos": ipos,
        "subCategories": mock_data.ipo_hub_data()["subCategories"],
    }


def get_ipo_hub_data():
    return cache.get_or_fetch(CACHE_KEY, CACHE_TTL_SECONDS, _fetch_all)
