import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Ported from templates/capabilities.html. The `categories` data below is
// copied as-is from mock_data.py's capabilities_data() for this Phase-1
// proof page — whether pages like this stay static-in-React or move to a
// real /api endpoint is the explicit mock_data.py decision deferred to
// Phase 4 of the rewrite plan, not resolved here.
const categories = [
  {
    kicker: "Category 01", title: "Market Data & News", iconBg: "#EEEDFD", iconColor: "#4640DE", checkBg: "#EEEDFD",
    desc: "Live NSE/BSE prices, index levels and curated news — the read on the market before you make a move.",
    items: [
      { title: "Real-time quotes", desc: "NSE & BSE cash market, < 200ms feed" },
      { title: "Index tracking", desc: "NIFTY, SENSEX, sectoral indices" },
      { title: "Curated news feed", desc: "Markets, IPO, economy, corporate" },
      { title: "Daily market digest", desc: "Overnight global cues, key levels" },
      { title: "Market movers", desc: "Top gainers, losers, volume spikes" },
      { title: "Corporate announcements", desc: "Results, filings, board actions" },
    ],
  },
  {
    kicker: "Category 02", title: "Stock Research & Fundamentals", iconBg: "#E6F7F1", iconColor: "#17A673", checkBg: "#E6F7F1",
    desc: "Go from a ticker to a decision — fundamentals, ratios, quarterly history and analyst sentiment for 2,100+ companies.",
    items: [
      { title: "Company fundamentals", desc: "P/E, ROE, debt, book value & more" },
      { title: "Multi-year financials", desc: "P&L, balance sheet, cash flow" },
      { title: "Quarterly results tracker", desc: "6-quarter revenue & profit trend" },
      { title: "Peer comparison", desc: "Benchmark against sector peers" },
      { title: "Analyst ratings", desc: "Buy/hold/sell consensus & targets" },
      { title: "Shareholding pattern", desc: "Promoter, FII, DII, public split" },
    ],
  },
  {
    kicker: "Category 03", title: "Trading Intelligence", iconBg: "#FBF2E1", iconColor: "#B98A2E", checkBg: "#FBF2E1",
    desc: "Screen the whole market, then trade off a fast, indicator-rich chart — built for daily technical workflows.",
    items: [
      { title: "Technical scanner", desc: "40+ filters — RSI, breakouts, volume" },
      { title: "Fundamental screener", desc: "Screen by ratios & growth metrics" },
      { title: "Saved & scheduled scans", desc: "Re-run your strategy automatically" },
      { title: "Live candlestick charts", desc: "Multi-timeframe, 30+ indicators" },
      { title: "Custom watchlists", desc: "Unlimited lists on paid plans" },
      { title: "Price & scan alerts", desc: "Push and email notifications" },
    ],
  },
  {
    kicker: "Category 04", title: "IPO Intelligence", iconBg: "#FCEBEA", iconColor: "#E0473F", checkBg: "#FCEBEA",
    desc: "Everything for primary-market investing — from DRHP to listing day, in one calendar.",
    items: [
      { title: "IPO calendar", desc: "Upcoming, ongoing & recently listed" },
      { title: "Live GMP tracking", desc: "Grey market premium, updated daily" },
      { title: "Subscription data", desc: "By category — QIB, NII, retail" },
      { title: "DRHP & RHP access", desc: "One-click document downloads" },
      { title: "Listing-day alerts", desc: "Get notified the moment shares list" },
      { title: "Allotment status check", desc: "Track applications across IPOs" },
    ],
  },
  {
    kicker: "Category 05", title: "Education & Advisory", iconBg: "#EEEDFD", iconColor: "#4640DE", checkBg: "#EEEDFD",
    desc: "Structured learning that plugs directly into the tools above, so a lesson turns into a saved scan.",
    items: [
      { title: "6 structured course tracks", desc: "Beginner to advanced, 140+ videos" },
      { title: "Weekly live webinars", desc: "With research analysts & CAs" },
      { title: "Market glossary", desc: "Plain-language term explainers" },
      { title: "Course progress tracking", desc: "Pick up exactly where you left off" },
      { title: "Community forum", desc: "Ask questions, share strategies" },
      { title: "Quarterly strategy calls", desc: "1-on-1, Premium plan only" },
    ],
  },
];

export default function Capabilities() {
  const { login } = useAuth();

  return (
    <>
      <div style={{ width: "100%", padding: "76px 48px 0", textAlign: "center" }}>
        <div style={{ maxWidth: 680, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16, alignItems: "center" }}>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Capabilities</span>
          <h1 style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1.15 }}>Everything Quantile does for Indian investors</h1>
          <p style={{ fontSize: 16, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>
            Five product categories, one subscription — organized around how you actually move through a trading day, from morning news to end-of-day review.
          </p>
        </div>
      </div>

      <div style={{ width: "100%", padding: "56px 48px 0" }}>
        <div style={{ maxWidth: 1140, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
          {categories.map((cat) => (
            <div key={cat.title} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, padding: 36, display: "flex", gap: 40 }}>
              <div style={{ width: 300, flexShrink: 0, display: "flex", flexDirection: "column", gap: 14 }}>
                <div style={{ width: 46, height: 46, borderRadius: 12, background: cat.iconBg, display: "flex", alignItems: "center", justifyContent: "center", color: cat.iconColor }}>
                  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 17L8.5 10.5L12.5 14L19 5" />
                    <path d="M14 5H19V10" />
                  </svg>
                </div>
                <div>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: cat.iconColor, letterSpacing: "0.04em", textTransform: "uppercase" }}>{cat.kicker}</span>
                  <h2 style={{ fontSize: 21, fontWeight: 800, marginTop: 6 }}>{cat.title}</h2>
                </div>
                <p style={{ fontSize: 13.5, color: "#5B6270", lineHeight: 1.65, margin: 0 }}>{cat.desc}</p>
              </div>
              <div style={{ flex: 1, display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: "12px 24px", alignContent: "center" }}>
                {cat.items.map((it) => (
                  <div key={it.title} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, marginTop: 2 }}>
                      <circle cx="8" cy="8" r="8" fill={cat.checkBg} />
                      <path d="M4.5 8.2L6.8 10.5L11.5 5.5" stroke={cat.iconColor} strokeWidth="1.6" fill="none" />
                    </svg>
                    <div>
                      <span style={{ fontSize: 13.5, fontWeight: 700, display: "block" }}>{it.title}</span>
                      <span style={{ fontSize: 12.5, color: "#5B6270", lineHeight: 1.5 }}>{it.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", padding: "64px 48px 88px" }}>
        <div style={{ maxWidth: 1140, margin: "0 auto", background: "#14171F", borderRadius: 20, padding: "44px 52px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 40 }}>
          <div style={{ maxWidth: 480, display: "flex", flexDirection: "column", gap: 10 }}>
            <h2 style={{ color: "white", fontSize: 25, fontWeight: 800 }}>See every capability in your own workflow</h2>
            <p style={{ color: "#9297A8", fontSize: 14, lineHeight: 1.6, margin: 0 }}>Start on the free plan — no card required — and upgrade when you need real-time data and the full scanner.</p>
          </div>
          <div style={{ display: "flex", gap: 12, flexShrink: 0 }}>
            <button type="button" onClick={login} style={{ background: "#4640DE", color: "white", fontSize: 14, fontWeight: 700, padding: "13px 24px", borderRadius: 10, border: "none", cursor: "pointer" }}>
              Start free
            </button>
            <Link to="/" style={{ border: "1.5px solid #3A3E4D", color: "white", fontSize: 14, fontWeight: 600, padding: "13px 22px", borderRadius: 10 }}>
              Compare plans
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}
