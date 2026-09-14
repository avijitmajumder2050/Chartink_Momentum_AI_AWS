"""MarketSmith India connector — EPS Strength & Price Strength ratings.

marketsmithindia.com's evaluation page is a JS app that renders these
ratings client-side (same situation as investorgain.com in ipo_connector.py
— a plain `requests` fetch gets an empty shell; only a rendered browser
sees the filled-in values), so this uses Playwright the same way.

Best-effort/supplementary: unlike screener.in's financials, a failed fetch
here should not take down the whole Stock Research page — callers should
treat an exception as "these two fields aren't available this time", not
fall back to substitute data.
"""

from playwright.sync_api import sync_playwright

from connectors import cache

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Ratings update at most daily and a headless render is expensive, so cache
# far longer than the screener.in fundamentals cache.
CACHE_TTL_SECONDS = 24 * 60 * 60

# "4" shows as a stale placeholder before the real rating finishes loading
# client-side (observed empirically, same guard used in the source script
# this connector is adapted from).
PLACEHOLDER_VALUES = {"N/A", "4", ""}


def _extract_metrics(page):
    return page.evaluate("""
        () => {
            function getVal(label) {
                const els = document.querySelectorAll("h4.modal-title");
                for (const el of els) {
                    if (el.innerText.includes(label)) {
                        const b = el.querySelector("b");
                        if (b) return b.innerText.trim();
                    }
                }
                return "N/A";
            }
            return {
                epsStrength: getVal("EPS Strength"),
                priceStrength: getVal("Price Strength"),
            };
        }
    """)


def _fetch(symbol):
    url = f"https://marketsmithindia.com/mstool/eval/{symbol.lower()}/evaluation.jsp#/"

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=25000, wait_until="domcontentloaded")

            metrics = {"epsStrength": "N/A", "priceStrength": "N/A"}
            for attempt in range(3):
                page.wait_for_timeout(min(800 * (attempt + 1), 2000))
                metrics = _extract_metrics(page)
                if metrics["epsStrength"] not in PLACEHOLDER_VALUES:
                    return metrics

            raise RuntimeError(f"marketsmithindia.com never rendered ratings for {symbol!r}")
        finally:
            browser.close()


def get_strength_ratings(symbol):
    key = f"marketsmith_strength_{symbol.upper()}"
    return cache.get_or_fetch(key, CACHE_TTL_SECONDS, lambda: _fetch(symbol))
