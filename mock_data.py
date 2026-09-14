# Placeholder content for the Quantile pages that aren't backed by a real
# data source yet (Phase 1 covers auth + dashboard + chart + one scanner;
# IPO/Fundamentals/News get real scrapers in Phase 2 — see project memory
# "quantile_architecture"). Shaped to match the fields the templates already
# render, so swapping a function body for a real query later needs no
# template changes.


def home_data():
    return {
        "watchlist": [
            {"symbol": "RELIANCE", "name": "Reliance Industries", "price": "2,945.60", "change": "+1.24%", "changeColor": "#17A673"},
            {"symbol": "TCS", "name": "Tata Consultancy Svcs", "price": "4,102.15", "change": "-0.38%", "changeColor": "#E0473F"},
            {"symbol": "HDFCBANK", "name": "HDFC Bank", "price": "1,678.90", "change": "+0.62%", "changeColor": "#17A673"},
            {"symbol": "INFY", "name": "Infosys", "price": "1,912.40", "change": "+2.05%", "changeColor": "#17A673"},
        ],
        "indices": [
            {"name": "NIFTY 50", "value": "24,812.35", "change": "+142.60 (0.58%)", "color": "#4ADE9C"},
            {"name": "SENSEX", "value": "81,540.12", "change": "+461.20 (0.57%)", "color": "#4ADE9C"},
            {"name": "BANK NIFTY", "value": "51,203.75", "change": "-89.40 (0.17%)", "color": "#F87171"},
            {"name": "NIFTY IT", "value": "39,880.60", "change": "+310.15 (0.78%)", "color": "#4ADE9C"},
        ],
        "features": [
            {"title": "IPO Hub", "desc": "Track upcoming, ongoing and listed IPOs with live GMP and subscription data.", "iconBg": "#EEEDFD", "iconColor": "#4640DE", "endpoint": "ipo_hub"},
            {"title": "Stock Research", "desc": "Fundamentals, analyst ratings and peer comparisons for 2,100+ listed companies.", "iconBg": "#E6F7F1", "iconColor": "#17A673", "endpoint": "research"},
            {"title": "Scanner", "desc": "Screen the entire market on RSI, breakouts, volume surges and 40+ filters.", "iconBg": "#FBF2E1", "iconColor": "#B98A2E", "endpoint": "scanner_page"},
            {"title": "Charts", "desc": "Fast candlestick charting with 30+ indicators and multi-timeframe views.", "iconBg": "#FCEBEA", "iconColor": "#E0473F", "endpoint": "chart_page"},
            {"title": "Education", "desc": "Structured courses and live webinars from beginner to advanced trading.", "iconBg": "#EEEDFD", "iconColor": "#4640DE", "endpoint": "education"},
        ],
        "testimonials": [
            {"quote": "The GMP tracking alone paid for my subscription in the first IPO season.", "name": "Rohan Deshmukh", "role": "Retail investor, Pune", "initials": "RD", "avatarBg": "#4640DE"},
            {"quote": "Finally a scanner that understands Indian market hours and circuit limits.", "name": "Ananya Iyer", "role": "Swing trader, Bengaluru", "initials": "AI", "avatarBg": "#17A673"},
            {"quote": "Started with the free course track, now I actually read balance sheets.", "name": "Vikram Shah", "role": "New investor, Ahmedabad", "initials": "VS", "avatarBg": "#B98A2E"},
        ],
    }


def news_data():
    return {
        "stories": [
            {"tag": "IPO", "tagColor": "#B98A2E", "tagBg": "#FBF2E1", "time": "1h ago", "headline": "Aravind Precision Engineering IPO subscribed 18.4x on final day, GMP holds at 15%", "source": "Quantile Desk", "thumbBg": "#4640DE"},
            {"tag": "ECONOMY", "tagColor": "#4640DE", "tagBg": "#EEEDFD", "time": "3h ago", "headline": "RBI keeps repo rate unchanged at 6.5%, flags festive-season inflation risk", "source": "Quantile Desk", "thumbBg": "#17A673"},
            {"tag": "CORPORATE", "tagColor": "#E0473F", "tagBg": "#FCEBEA", "time": "5h ago", "headline": "Tata Steel Q2 net profit beats estimates on lower coking coal costs", "source": "Quantile Desk", "thumbBg": "#B98A2E"},
            {"tag": "GLOBAL", "tagColor": "#5B6270", "tagBg": "#F0F1F4", "time": "7h ago", "headline": "US Fed signals one more rate cut in 2026 as inflation cools toward target", "source": "Quantile Desk", "thumbBg": "#14171F"},
            {"tag": "MARKETS", "tagColor": "#F2A93B", "tagBg": "#FBF2E1", "time": "9h ago", "headline": "FIIs turn net buyers for the first time in six weeks, infuse ₹4,200 Cr", "source": "Quantile Desk", "thumbBg": "#4640DE"},
            {"tag": "CORPORATE", "tagColor": "#E0473F", "tagBg": "#FCEBEA", "time": "11h ago", "headline": "Zomato announces ₹1,200 Cr buyback, stock jumps 6% in early trade", "source": "Quantile Desk", "thumbBg": "#17A673"},
        ],
        "trending": [
            {"rank": "01", "headline": "RBI monetary policy: 5 key takeaways for investors"},
            {"rank": "02", "headline": "Why GMP crashed for 3 IPOs this week"},
            {"rank": "03", "headline": "Bank NIFTY technical outlook ahead of expiry"},
            {"rank": "04", "headline": "FPI flows turn positive after six-week outflow streak"},
            {"rank": "05", "headline": "Q2 earnings calendar: 40 companies reporting this week"},
        ],
        "gainers": [
            {"symbol": "DIXON", "change": "+6.72%"},
            {"symbol": "ZOMATO", "change": "+5.90%"},
            {"symbol": "TATASTEEL", "change": "+4.82%"},
        ],
        "losers": [
            {"symbol": "INDUSINDBK", "change": "-3.14%"},
            {"symbol": "AXISBANK", "change": "-1.86%"},
            {"symbol": "WIPRO", "change": "-1.22%"},
        ],
    }


def capabilities_data():
    return {
        "categories": [
            {
                "kicker": "Category 01", "title": "Market Data & News", "iconBg": "#EEEDFD", "iconColor": "#4640DE", "checkBg": "#EEEDFD",
                "desc": "Live NSE/BSE prices, index levels and curated news — the read on the market before you make a move.",
                "items": [
                    {"title": "Real-time quotes", "desc": "NSE & BSE cash market, < 200ms feed"},
                    {"title": "Index tracking", "desc": "NIFTY, SENSEX, sectoral indices"},
                    {"title": "Curated news feed", "desc": "Markets, IPO, economy, corporate"},
                    {"title": "Daily market digest", "desc": "Overnight global cues, key levels"},
                    {"title": "Market movers", "desc": "Top gainers, losers, volume spikes"},
                    {"title": "Corporate announcements", "desc": "Results, filings, board actions"},
                ],
            },
            {
                "kicker": "Category 02", "title": "Stock Research & Fundamentals", "iconBg": "#E6F7F1", "iconColor": "#17A673", "checkBg": "#E6F7F1",
                "desc": "Go from a ticker to a decision — fundamentals, ratios, quarterly history and analyst sentiment for 2,100+ companies.",
                "items": [
                    {"title": "Company fundamentals", "desc": "P/E, ROE, debt, book value & more"},
                    {"title": "Multi-year financials", "desc": "P&L, balance sheet, cash flow"},
                    {"title": "Quarterly results tracker", "desc": "6-quarter revenue & profit trend"},
                    {"title": "Peer comparison", "desc": "Benchmark against sector peers"},
                    {"title": "Analyst ratings", "desc": "Buy/hold/sell consensus & targets"},
                    {"title": "Shareholding pattern", "desc": "Promoter, FII, DII, public split"},
                ],
            },
            {
                "kicker": "Category 03", "title": "Trading Intelligence", "iconBg": "#FBF2E1", "iconColor": "#B98A2E", "checkBg": "#FBF2E1",
                "desc": "Screen the whole market, then trade off a fast, indicator-rich chart — built for daily technical workflows.",
                "items": [
                    {"title": "Technical scanner", "desc": "40+ filters — RSI, breakouts, volume"},
                    {"title": "Fundamental screener", "desc": "Screen by ratios & growth metrics"},
                    {"title": "Saved & scheduled scans", "desc": "Re-run your strategy automatically"},
                    {"title": "Live candlestick charts", "desc": "Multi-timeframe, 30+ indicators"},
                    {"title": "Custom watchlists", "desc": "Unlimited lists on paid plans"},
                    {"title": "Price & scan alerts", "desc": "Push and email notifications"},
                ],
            },
            {
                "kicker": "Category 04", "title": "IPO Intelligence", "iconBg": "#FCEBEA", "iconColor": "#E0473F", "checkBg": "#FCEBEA",
                "desc": "Everything for primary-market investing — from DRHP to listing day, in one calendar.",
                "items": [
                    {"title": "IPO calendar", "desc": "Upcoming, ongoing & recently listed"},
                    {"title": "Live GMP tracking", "desc": "Grey market premium, updated daily"},
                    {"title": "Subscription data", "desc": "By category — QIB, NII, retail"},
                    {"title": "DRHP & RHP access", "desc": "One-click document downloads"},
                    {"title": "Listing-day alerts", "desc": "Get notified the moment shares list"},
                    {"title": "Allotment status check", "desc": "Track applications across IPOs"},
                ],
            },
            {
                "kicker": "Category 05", "title": "Education & Advisory", "iconBg": "#EEEDFD", "iconColor": "#4640DE", "checkBg": "#EEEDFD",
                "desc": "Structured learning that plugs directly into the tools above, so a lesson turns into a saved scan.",
                "items": [
                    {"title": "6 structured course tracks", "desc": "Beginner to advanced, 140+ videos"},
                    {"title": "Weekly live webinars", "desc": "With research analysts & CAs"},
                    {"title": "Market glossary", "desc": "Plain-language term explainers"},
                    {"title": "Course progress tracking", "desc": "Pick up exactly where you left off"},
                    {"title": "Community forum", "desc": "Ask questions, share strategies"},
                    {"title": "Quarterly strategy calls", "desc": "1-on-1, Premium plan only"},
                ],
            },
        ],
    }


def education_data():
    return {
        "courses": [
            {"title": "Markets 101: Your First Trade", "level": "Beginner", "levelColor": "#17A673", "levelBg": "#E6F7F1", "desc": "Demat accounts, order types and how NSE/BSE settlement actually works.", "lessons": 18, "duration": "3h 20m", "cta": "Start free", "bannerBg": "#4640DE"},
            {"title": "Reading a Balance Sheet", "level": "Beginner", "levelColor": "#17A673", "levelBg": "#E6F7F1", "desc": "P/E, ROE and debt ratios explained with real Indian company filings.", "lessons": 16, "duration": "2h 55m", "cta": "Start free", "bannerBg": "#17A673"},
            {"title": "Technical Analysis Foundations", "level": "Intermediate", "levelColor": "#B98A2E", "levelBg": "#FBF2E1", "desc": "Candlestick patterns, support/resistance and moving averages in practice.", "lessons": 24, "duration": "6h 40m", "cta": "View course", "bannerBg": "#B98A2E"},
            {"title": "IPO Investing Playbook", "level": "Intermediate", "levelColor": "#B98A2E", "levelBg": "#FBF2E1", "desc": "How to read a DRHP, judge GMP signals and size an application.", "lessons": 12, "duration": "2h 10m", "cta": "View course", "bannerBg": "#4640DE"},
            {"title": "Options Strategy Lab", "level": "Advanced", "levelColor": "#E0473F", "levelBg": "#FCEBEA", "desc": "Covered calls, spreads and hedging with NIFTY & Bank NIFTY options.", "lessons": 30, "duration": "8h 15m", "cta": "View course", "bannerBg": "#14171F"},
            {"title": "Building a Screener Strategy", "level": "Advanced", "levelColor": "#E0473F", "levelBg": "#FCEBEA", "desc": "Turn a trading thesis into a repeatable Quantile scanner query.", "lessons": 14, "duration": "3h 45m", "cta": "View course", "bannerBg": "#17A673"},
        ],
        "curriculum": [
            {"num": "01", "title": "Why price action matters more than news", "duration": "18 min"},
            {"num": "02", "title": "Candlestick anatomy and core patterns", "duration": "32 min"},
            {"num": "03", "title": "Support, resistance and trendlines", "duration": "27 min"},
            {"num": "04", "title": "Moving averages and crossovers", "duration": "24 min"},
            {"num": "05", "title": "RSI, MACD and applying them in Scanner", "duration": "35 min"},
        ],
        "webinars": [
            {"tag": "LIVE Thu, 6 PM", "tagColor": "#E0473F", "tagBg": "#FCEBEA", "date": "22 Aug", "title": "Reading GMP signals ahead of the festive IPO season", "host": "Rhea Kapoor, Research Lead", "seats": "340 registered"},
            {"tag": "Upcoming", "tagColor": "#4640DE", "tagBg": "#EEEDFD", "date": "27 Aug", "title": "Building your first scanner-based watchlist", "host": "CA Meera Rangan", "seats": "128 registered"},
            {"tag": "Upcoming", "tagColor": "#4640DE", "tagBg": "#EEEDFD", "date": "2 Sep", "title": "Bank NIFTY options: a beginner-safe framework", "host": "Arjun Nair, Derivatives Analyst", "seats": "96 registered"},
        ],
    }


def pricing_data():
    return {
        "plans": [
            {"name": "Free", "tagline": "Get a feel for the market", "price": "₹0", "period": "/ forever", "cardBg": "#FFFFFF", "border": "1px solid #E3E6EC", "titleColor": "#14171F", "subColor": "#5B6270", "ctaBg": "#F0F1F4", "ctaColor": "#14171F", "cta": "Current plan", "checkBg": "#E9EAF0", "checkColor": "#5B6270", "featured": False,
             "features": ["Delayed market quotes (15 min)", "IPO calendar, no GMP alerts", "5 stocks in watchlist", "Markets 101 course track", "Community forum access"]},
            {"name": "Pro", "tagline": "For active retail investors", "price": "₹499", "period": "/ month", "cardBg": "#14171F", "border": "2px solid #4640DE", "titleColor": "#FFFFFF", "subColor": "#9297A8", "ctaBg": "#4640DE", "ctaColor": "#FFFFFF", "cta": "Start 7-day free trial", "checkBg": "#2A2E3A", "checkColor": "#4ADE9C", "featured": True,
             "features": ["Real-time NSE/BSE quotes", "Live GMP tracking & alerts", "Unlimited watchlist", "Full technical scanner", "All 6 course tracks", "Weekly live webinars"]},
            {"name": "Premium", "tagline": "For serious traders & analysts", "price": "₹1,299", "period": "/ month", "cardBg": "#FFFFFF", "border": "1px solid #E3E6EC", "titleColor": "#14171F", "subColor": "#5B6270", "ctaBg": "#FBF2E1", "ctaColor": "#B98A2E", "cta": "Start 7-day free trial", "checkBg": "#FBF2E1", "checkColor": "#B98A2E", "featured": False,
             "features": ["Everything in Pro", "Advanced options screener", "Peer & sector deep research", "Priority support (15 min SLA)", "1-on-1 quarterly strategy call", "API access for your own tools"]},
        ],
        "comparisonRows": [
            {"label": "Market data delay", "free": "15 min", "pro": "Real-time", "premium": "Real-time"},
            {"label": "IPO GMP alerts", "free": "—", "pro": "Yes", "premium": "Yes"},
            {"label": "Scanner filters", "free": "3", "pro": "40+", "premium": "40+ & custom"},
            {"label": "Watchlist size", "free": "5 stocks", "pro": "Unlimited", "premium": "Unlimited"},
            {"label": "Chart indicators", "free": "3", "pro": "30+", "premium": "30+"},
            {"label": "Course tracks", "free": "1", "pro": "6", "premium": "6 + workshops"},
            {"label": "Support", "free": "Community", "pro": "Email, 24h", "premium": "Priority, 15 min"},
        ],
        "faqs": [
            {"q": "Is Quantile a SEBI-registered advisor?", "a": "No. Quantile is a research and analytics platform. Data, scores and screeners are for informational purposes only and are not investment advice."},
            {"q": "Can I cancel my subscription anytime?", "a": "Yes, cancel from your account settings anytime — you keep access until the end of the billing period, no questions asked."},
            {"q": "What payment methods do you accept?", "a": "UPI, all major debit/credit cards, and net banking through our RBI-compliant payment partner."},
            {"q": "Do you offer a student or annual discount?", "a": "Annual billing saves 20% versus monthly. Verified students get an additional 15% off Pro with a valid .edu or college ID."},
            {"q": "Is my payment and personal data secure?", "a": "Yes — payments are processed by a PCI-DSS compliant gateway; we never store your card details on Quantile servers."},
        ],
    }


def vision_data():
    return {
        "values": [
            {"num": "01", "title": "Radical transparency", "desc": "Every score and screener criterion is documented — no black-box \"buy signals.\""},
            {"num": "02", "title": "India-first design", "desc": "Built around NSE/BSE market structure, circuit limits and settlement cycles."},
            {"num": "03", "title": "Education over hype", "desc": "We teach the \"why\" behind every metric, not just a green or red signal."},
            {"num": "04", "title": "Accessible pricing", "desc": "A serious research stack should cost less than a weekly food delivery order."},
        ],
        "timeline": [
            {"year": "2022", "title": "Quantile founded in Mumbai", "desc": "Three engineers and a chartered accountant, frustrated by scattered IPO data."},
            {"year": "2023", "title": "IPO Hub & GMP tracking launch", "desc": "Real-time grey market premium tracking across 60+ IPOs in the first year."},
            {"year": "2024", "title": "Crossed 5 lakh investors", "desc": "Stock Research and the first course track, \"Markets 101,\" go live."},
            {"year": "2025", "title": "Scanner & live charting launch", "desc": "Full technical screener with 40+ filters and multi-timeframe charts."},
            {"year": "2026", "title": "12.4 lakh investors and counting", "desc": "Education platform expands to 6 course tracks and live weekly webinars."},
        ],
    }


def ipo_hub_data():
    return {
        "ipos": [
            {"name": "Aravind Precision Eng.", "segment": "Mainboard", "initials": "AP", "logoBg": "#4640DE", "tag": "Closing today", "tagBg": "#FCEBEA", "tagColor": "#E0473F", "priceBand": "₹412–435", "lot": "34 shares", "gmp": "+₹68 (15.6%)", "subLabel": "18.4x", "subPct": "100%", "closes": "20 Aug"},
            {"name": "Suryoday Fintech", "segment": "SME", "initials": "SF", "logoBg": "#17A673", "tag": "Open", "tagBg": "#E6F7F1", "tagColor": "#17A673", "priceBand": "₹96–102", "lot": "120 shares", "gmp": "+₹22 (21.6%)", "subLabel": "4.2x", "subPct": "62%", "closes": "22 Aug"},
            {"name": "Kalpataru Green Energy", "segment": "Mainboard", "initials": "KG", "logoBg": "#B98A2E", "tag": "Open", "tagBg": "#E6F7F1", "tagColor": "#17A673", "priceBand": "₹255–268", "lot": "55 shares", "gmp": "+₹14 (5.2%)", "subLabel": "2.1x", "subPct": "38%", "closes": "23 Aug"},
            {"name": "Vantage Logistics Park", "segment": "Mainboard", "initials": "VL", "logoBg": "#5B6270", "tag": "Upcoming", "tagBg": "#FBF2E1", "tagColor": "#B98A2E", "priceBand": "TBA", "lot": "TBA", "gmp": "GMP TBA", "subLabel": "-", "subPct": "0%", "closes": "28 Aug"},
            {"name": "Nimbus Data Centers", "segment": "Mainboard", "initials": "ND", "logoBg": "#4640DE", "tag": "Upcoming", "tagBg": "#FBF2E1", "tagColor": "#B98A2E", "priceBand": "TBA", "lot": "TBA", "gmp": "GMP TBA", "subLabel": "-", "subPct": "0%", "closes": "02 Sep"},
            {"name": "Prasol Chemicals", "segment": "SME", "initials": "PC", "logoBg": "#17A673", "tag": "Closed", "tagBg": "#F0F1F4", "tagColor": "#5B6270", "priceBand": "₹188–198", "lot": "75 shares", "gmp": "+₹31 (15.7%)", "subLabel": "12.6x", "subPct": "100%", "closes": "11 Aug"},
            {"name": "Coral Marine Foods", "segment": "SME", "initials": "CM", "logoBg": "#E0473F", "tag": "Closed", "tagBg": "#F0F1F4", "tagColor": "#5B6270", "priceBand": "₹64–68", "lot": "200 shares", "gmp": "-₹4 (-5.9%)", "subLabel": "1.8x", "subPct": "100%", "closes": "05 Aug"},
        ],
        "subCategories": [
            {"label": "QIB", "value": "32.4x", "pct": "95%", "color": "#4640DE"},
            {"label": "NII (HNI)", "value": "21.8x", "pct": "80%", "color": "#4640DE"},
            {"label": "Retail", "value": "9.6x", "pct": "55%", "color": "#17A673"},
            {"label": "Employee", "value": "3.2x", "pct": "30%", "color": "#B98A2E"},
        ],
    }


def research_data(symbol=None):
    return {
        "symbol": (symbol or "HDFCBANK").upper(),
        "header": {
            "name": "HDFC Bank Ltd",
            "initials": "HD",
            "price": "₹1,678.90",
            "changePct": "0.62%",
            "direction": "up",
        },
        "fundamentals": [
            {"label": "Market Cap", "value": "₹12.8 L Cr"},
            {"label": "P/E Ratio", "value": "19.4x"},
            {"label": "P/B Ratio", "value": "2.8x"},
            {"label": "Dividend Yield", "value": "1.12%"},
            {"label": "ROE", "value": "16.8%"},
            {"label": "Debt / Equity", "value": "0.42"},
            {"label": "Face Value", "value": "₹1"},
            {"label": "Book Value", "value": "₹598.10"},
        ],
        "peers": [
            {"name": "ICICI Bank", "cmp": "1,284.50", "pe": "18.2x", "mcap": "₹9.1 L Cr", "ret": "+22.4%", "retColor": "#17A673"},
            {"name": "Kotak Mahindra Bank", "cmp": "1,842.20", "pe": "20.6x", "mcap": "₹3.7 L Cr", "ret": "+8.1%", "retColor": "#17A673"},
            {"name": "Axis Bank", "cmp": "1,152.75", "pe": "15.9x", "mcap": "₹3.6 L Cr", "ret": "-3.6%", "retColor": "#E0473F"},
            {"name": "IndusInd Bank", "cmp": "968.40", "pe": "11.3x", "mcap": "₹0.8 L Cr", "ret": "-14.2%", "retColor": "#E0473F"},
        ],
    }




def subscriber_dashboard_data():
    return {
        "quick_nav_endpoints": {
            "Live Chart": "chart_page",
            "Stock Research": "research",
            "IPO Hub": "ipo_hub",
            "Scanner": "scanner_page",
            "Education": "education",
        },
        "quickNav": [
            {"label": "Live Chart", "bg": "#EEEDFD", "color": "#4640DE", "icon": "chart"},
            {"label": "Stock Research", "bg": "#E6F7F1", "color": "#17A673", "icon": "search"},
            {"label": "IPO Hub", "bg": "#FBF2E1", "color": "#B98A2E", "icon": "building"},
            {"label": "Scanner", "bg": "#FCEBEA", "color": "#E0473F", "icon": "target"},
            {"label": "Education", "bg": "#EEEDFD", "color": "#4640DE", "icon": "book"},
        ],
    }


