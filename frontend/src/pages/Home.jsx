import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../api/client";

// Market data here is live — GET /api/home (app.py): the index strip,
// today's top movers and market breadth, from the same Dhan-backed data
// the dashboard uses. The marketing copy below deliberately makes no
// numeric claims (user counts, ratings, accuracy/latency figures) and has
// no testimonials — the originals from mock_data.py were placeholders,
// not real figures.
const REFRESH_MS = 60 * 1000;

const FEATURES = [
  { title: "IPO Hub", desc: "Track upcoming, ongoing and listed IPOs with GMP and subscription data.", iconBg: "#EEEDFD", iconColor: "#4640DE", to: "/markets/ipo-hub" },
  { title: "Stock Research", desc: "Fundamentals, financials and peer comparisons for NSE-listed companies.", iconBg: "#E6F7F1", iconColor: "#17A673", to: "/markets/research" },
  { title: "Scanner", desc: "Momentum, breakout and volume scanners — with circuit-locked stocks filtered out.", iconBg: "#FBF2E1", iconColor: "#B98A2E", to: "/scanner" },
  { title: "Charts", desc: "Fast candlestick charts on live NSE prices, with multi-timeframe views.", iconBg: "#FCEBEA", iconColor: "#E0473F", to: "/markets/chart" },
  { title: "Education", desc: "Structured courses from beginner basics to advanced trading.", iconBg: "#EEEDFD", iconColor: "#4640DE", to: "/education" },
];

const WHY = [
  { title: "Circuit-aware scanning", desc: "Stocks frozen at their circuit limit, or on a 5% band, are excluded before they ever reach a scan result." },
  { title: "Order wins as they're filed", desc: "Company order and contract wins straight from NSE/BSE filings, alongside market news, on the News page." },
  { title: "Live NSE data", desc: "Index levels, quotes and charts from a live exchange-connected feed — not delayed snapshots." },
];

const fmt = (n, digits = 2) => Number(n).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const signed = (n, digits = 2) => `${n >= 0 ? "+" : ""}${fmt(n, digits)}`;

function istTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
}

function MoverRow({ m }) {
  const up = m.changePct >= 0;
  return (
    <Link to={`/markets/chart?symbol=${encodeURIComponent(m.symbol)}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid #F0F1F4", color: "inherit", textDecoration: "none" }}>
      <span style={{ fontWeight: 600, fontSize: 14.5 }}>{m.symbol}</span>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
        {m.price != null && <span className="num" style={{ fontWeight: 600, fontSize: 14.5 }}>₹{fmt(m.price)}</span>}
        <span className="num" style={{ fontSize: 12.5, fontWeight: 600, color: up ? "#17A673" : "#E0473F" }}>{signed(m.changePct)}%</span>
      </div>
    </Link>
  );
}

export default function Home() {
  const { user, login } = useAuth();
  const [market, setMarket] = useState(null);
  const [moverTab, setMoverTab] = useState("gainers");

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = () => {
      apiFetch("/api/home")
        .then((res) => res.json())
        .then((d) => !cancelled && setMarket(d))
        .catch(() => {}) // marketing page still renders fine without live data
        .finally(() => {
          if (!cancelled) timer = setTimeout(load, REFRESH_MS);
        });
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const indices = market?.indices || [];
  const movers = market?.[moverTab] || [];
  const breadth = market?.breadth;

  return (
    <>
      <div style={{ width: "100%", background: "linear-gradient(180deg, #F1F0FD 0%, #FAF9F6 62%)", padding: "88px clamp(16px, 5vw, 48px) 72px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 40, alignItems: "center" }}>
          <div style={{ flex: "1.1 1 320px", display: "flex", flexDirection: "column", gap: 26 }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "#EEEDFD", color: "#4640DE", fontSize: 13, fontWeight: 600, padding: "7px 14px", borderRadius: 100, width: "fit-content" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#17A673" }} />
              Live NSE market data
            </div>
            <h1 style={{ fontSize: "clamp(32px, 6vw, 54px)", lineHeight: 1.12, fontWeight: 800, letterSpacing: "-0.02em", color: "#14171F" }}>
              Research smarter.<br />Invest in Indian markets<br />with confidence.
            </h1>
            <p style={{ fontSize: 18, lineHeight: 1.65, color: "#5B6270", maxWidth: 480, margin: 0 }}>
              IPO tracking, stock research, technical scanners and live charts — plus the courses to actually understand them. One subscription, built for India.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", paddingTop: 4 }}>
              {user ? (
                <Link to="/dashboard" style={{ background: "#4640DE", color: "white", fontSize: 15, fontWeight: 700, padding: "15px 28px", borderRadius: 10 }}>Go to dashboard</Link>
              ) : (
                <button type="button" onClick={login} style={{ background: "#4640DE", color: "white", fontSize: 15, fontWeight: 700, padding: "15px 28px", borderRadius: 10, border: "none", cursor: "pointer" }}>
                  Start free — no card needed
                </button>
              )}
              <Link to="/scanner" style={{ background: "transparent", color: "#14171F", fontSize: 15, fontWeight: 600, padding: "15px 22px", borderRadius: 10, border: "1.5px solid #D8DAE3", display: "flex", alignItems: "center", gap: 8 }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M5.5 3.5L11.5 8L5.5 12.5V3.5Z" fill="#14171F" /></svg>
                See it in action
              </Link>
            </div>
            {breadth?.sampleSize > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 28, paddingTop: 12 }}>
                {[
                  [breadth.advancing, "advancing today", "#17A673"],
                  [breadth.declining, "declining today", "#E0473F"],
                  [breadth.sampleSize, "stocks tracked live", "#14171F"],
                ].map(([n, l, color]) => (
                  <div key={l} style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontFamily: "'Manrope', sans-serif", fontWeight: 800, fontSize: 22, color }}>{fmt(n, 0)}</span>
                    <span style={{ fontSize: 12.5, color: "#8A90A0" }}>{l}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ flex: "1 1 300px", display: "flex", justifyContent: "center" }}>
            <div style={{ width: "100%", maxWidth: 420, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, boxShadow: "0 20px 50px rgba(20,23,31,0.08)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 700, fontSize: 15 }}>Today's top movers</span>
                {market?.moversUpdatedAt && <span style={{ fontSize: 12, color: "#8A90A0" }}>Updated {istTime(market.moversUpdatedAt)}</span>}
              </div>
              <div style={{ display: "flex", gap: 6, background: "#F4F5F8", borderRadius: 9, padding: 3 }}>
                {[["gainers", "Gainers"], ["losers", "Losers"]].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setMoverTab(key)}
                    style={{
                      flex: 1, border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "7px 0", borderRadius: 7,
                      background: moverTab === key ? "#FFFFFF" : "transparent", color: moverTab === key ? "#14171F" : "#8A90A0",
                      boxShadow: moverTab === key ? "0 1px 3px rgba(20,23,31,0.08)" : "none",
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {movers.length ? (
                <div>{movers.map((m) => <MoverRow key={m.symbol} m={m} />)}</div>
              ) : (
                <p style={{ fontSize: 13, color: "#8A90A0", textAlign: "center", padding: "26px 0", margin: 0 }}>
                  {market ? "Today's movers are being calculated — check back in a minute." : "Loading live market data…"}
                </p>
              )}
              <div style={{ background: "#EEEDFD", borderRadius: 12, padding: "14px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, color: "#4640DE", fontWeight: 600 }}>Scan the market for today's breakouts</span>
                <Link to="/scanner" style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, whiteSpace: "nowrap" }}>View →</Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {indices.length > 0 && (
        <div style={{ width: "100%", background: "#14171F", padding: "18px clamp(16px, 5vw, 48px)" }}>
          <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px 24px" }}>
            {indices.map((idx) => {
              const up = idx.change >= 0;
              return (
                <div key={idx.label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: "#9297A8", fontSize: 13, fontWeight: 500 }}>{idx.label}</span>
                  <span className="num" style={{ color: "white", fontSize: 14.5, fontWeight: 600 }}>{fmt(idx.value)}</span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 600, color: up ? "#4ADE9C" : "#F87171" }}>
                    {signed(idx.change)} ({signed(idx.changePct)}%)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ width: "100%", padding: "88px clamp(16px, 5vw, 48px)", background: "#FAF9F6" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <div style={{ maxWidth: 560, marginBottom: 48 }}>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Everything in one place</span>
            <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.01em", marginTop: 10 }}>Five tools. One market view.</h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 20 }}>
            {FEATURES.map((f) => (
              <div key={f.title} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 26, display: "flex", flexDirection: "column", gap: 14 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: f.iconBg, display: "flex", alignItems: "center", justifyContent: "center", color: f.iconColor }}>
                  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 17L8.5 10.5L12.5 14L19 5" /><path d="M14 5H19V10" />
                  </svg>
                </div>
                <h3 style={{ fontSize: 17.5, fontWeight: 700 }}>{f.title}</h3>
                <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>{f.desc}</p>
                <Link to={f.to} style={{ fontSize: 13.5, fontWeight: 700, color: "#4640DE" }}>Explore {f.title} →</Link>
              </div>
            ))}
            <Link to="/education" style={{ background: "#4640DE", borderRadius: 16, padding: 26, display: "flex", flexDirection: "column", gap: 14, justifyContent: "center" }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: "white" }}>New to investing?</h3>
              <p style={{ fontSize: 14, color: "#C9CCFB", lineHeight: 1.6, margin: 0 }}>Start with the "Markets 101" course track — built for first-time investors.</p>
              <span style={{ fontSize: 13.5, fontWeight: 700, color: "white" }}>Start learning →</span>
            </Link>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "8px clamp(16px, 5vw, 48px) 88px", background: "#FAF9F6" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, padding: "clamp(24px, 5vw, 48px)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 40, flexWrap: "wrap" }}>
            <div style={{ maxWidth: 320 }}>
              <h2 style={{ fontSize: 28, fontWeight: 800 }}>Built for how Indian investors actually trade</h2>
              <p style={{ fontSize: 14.5, color: "#5B6270", lineHeight: 1.6, marginTop: 12 }}>Real NSE data, GMP tracking, and screeners tuned to Indian market structure — not a US product with rupee signs bolted on.</p>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 36, flex: 1 }}>
              {WHY.map((w) => (
                <div key={w.title}>
                  <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: 17, fontWeight: 800, color: "#4640DE" }}>{w.title}</span>
                  <p style={{ fontSize: 13.5, color: "#5B6270", lineHeight: 1.6, marginTop: 6 }}>{w.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 clamp(16px, 5vw, 48px) 88px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", background: "#14171F", borderRadius: 20, padding: "clamp(24px, 5vw, 48px) clamp(24px, 5vw, 56px)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 40, flexWrap: "wrap" }}>
          <div style={{ maxWidth: 480, display: "flex", flexDirection: "column", gap: 12 }}>
            <span style={{ color: "#F2A93B", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Quantile Pro</span>
            <h2 style={{ color: "white", fontSize: 28, fontWeight: 800 }}>Unlock scanners, deep research &amp; live charts</h2>
            <p style={{ color: "#9297A8", fontSize: 14.5, lineHeight: 1.6, margin: 0 }}>Starting at ₹499/month. Cancel anytime.</p>
          </div>
          <Link to="/pricing" style={{ background: "#4640DE", color: "white", fontSize: 14.5, fontWeight: 700, padding: "14px 26px", borderRadius: 10, flexShrink: 0 }}>See plans &amp; pricing</Link>
        </div>
      </div>
    </>
  );
}
