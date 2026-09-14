import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Ported from templates/home.html. Data below is copied from mock_data.
// py's home_data() — purely illustrative marketing content (fabricated
// example numbers/testimonials, same as the original app), so it's
// static-in-React rather than a new backend endpoint, matching the
// precedent set for Capabilities in Phase 1. See the rewrite plan's
// mock_data.py decision point.
const WATCHLIST = [
  { symbol: "RELIANCE", name: "Reliance Industries", price: "2,945.60", change: "+1.24%", changeColor: "#17A673" },
  { symbol: "TCS", name: "Tata Consultancy Svcs", price: "4,102.15", change: "-0.38%", changeColor: "#E0473F" },
  { symbol: "HDFCBANK", name: "HDFC Bank", price: "1,678.90", change: "+0.62%", changeColor: "#17A673" },
  { symbol: "INFY", name: "Infosys", price: "1,912.40", change: "+2.05%", changeColor: "#17A673" },
];
const INDICES = [
  { name: "NIFTY 50", value: "24,812.35", change: "+142.60 (0.58%)", color: "#4ADE9C" },
  { name: "SENSEX", value: "81,540.12", change: "+461.20 (0.57%)", color: "#4ADE9C" },
  { name: "BANK NIFTY", value: "51,203.75", change: "-89.40 (0.17%)", color: "#F87171" },
  { name: "NIFTY IT", value: "39,880.60", change: "+310.15 (0.78%)", color: "#4ADE9C" },
];
const FEATURES = [
  { title: "IPO Hub", desc: "Track upcoming, ongoing and listed IPOs with live GMP and subscription data.", iconBg: "#EEEDFD", iconColor: "#4640DE", to: "/markets/ipo-hub" },
  { title: "Stock Research", desc: "Fundamentals, analyst ratings and peer comparisons for 2,100+ listed companies.", iconBg: "#E6F7F1", iconColor: "#17A673", to: "/markets/research" },
  { title: "Scanner", desc: "Screen the entire market on RSI, breakouts, volume surges and 40+ filters.", iconBg: "#FBF2E1", iconColor: "#B98A2E", to: "/scanner" },
  { title: "Charts", desc: "Fast candlestick charting with 30+ indicators and multi-timeframe views.", iconBg: "#FCEBEA", iconColor: "#E0473F", to: "/markets/chart" },
  { title: "Education", desc: "Structured courses and live webinars from beginner to advanced trading.", iconBg: "#EEEDFD", iconColor: "#4640DE", to: "/education" },
];
const TESTIMONIALS = [
  { quote: "The GMP tracking alone paid for my subscription in the first IPO season.", name: "Rohan Deshmukh", role: "Retail investor, Pune", initials: "RD", avatarBg: "#4640DE" },
  { quote: "Finally a scanner that understands Indian market hours and circuit limits.", name: "Ananya Iyer", role: "Swing trader, Bengaluru", initials: "AI", avatarBg: "#17A673" },
  { quote: "Started with the free course track, now I actually read balance sheets.", name: "Vikram Shah", role: "New investor, Ahmedabad", initials: "VS", avatarBg: "#B98A2E" },
];

export default function Home() {
  const { user, login } = useAuth();

  return (
    <>
      <div style={{ width: "100%", background: "linear-gradient(180deg, #F1F0FD 0%, #FAF9F6 62%)", padding: "88px 48px 72px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", gap: 64, alignItems: "center" }}>
          <div style={{ flex: 1.1, display: "flex", flexDirection: "column", gap: 26 }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "#EEEDFD", color: "#4640DE", fontSize: 13, fontWeight: 600, padding: "7px 14px", borderRadius: 100, width: "fit-content" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#17A673" }} />
              Live NSE &amp; BSE data
            </div>
            <h1 style={{ fontSize: 54, lineHeight: 1.08, fontWeight: 800, letterSpacing: "-0.02em", color: "#14171F" }}>
              Research smarter.<br />Invest in Indian markets<br />with confidence.
            </h1>
            <p style={{ fontSize: 18, lineHeight: 1.65, color: "#5B6270", maxWidth: 480, margin: 0 }}>
              IPO tracking, stock research, technical scanners and live charts — plus the courses to actually understand them. One subscription, built for India.
            </p>
            <div style={{ display: "flex", gap: 14, alignItems: "center", paddingTop: 4 }}>
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
            <div style={{ display: "flex", gap: 28, paddingTop: 12 }}>
              {[["12.4L+", "investors onboard"], ["2,100+", "NSE/BSE stocks covered"], ["4.7 / 5", "on Play Store"]].map(([n, l]) => (
                <div key={l} style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontFamily: "'Manrope', sans-serif", fontWeight: 800, fontSize: 22 }}>{n}</span>
                  <span style={{ fontSize: 12.5, color: "#8A90A0" }}>{l}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
            <div style={{ width: "100%", maxWidth: 420, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, boxShadow: "0 20px 50px rgba(20,23,31,0.08)", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: 700, fontSize: 15 }}>Your Watchlist</span>
                <span style={{ fontSize: 12, color: "#8A90A0" }}>Today, 3:24 PM</span>
              </div>
              {WATCHLIST.map((stk) => (
                <div key={stk.symbol} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid #F0F1F4" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontWeight: 600, fontSize: 14.5 }}>{stk.symbol}</span>
                    <span style={{ fontSize: 12, color: "#8A90A0" }}>{stk.name}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span className="num" style={{ fontWeight: 600, fontSize: 14.5 }}>₹{stk.price}</span>
                    <span className="num" style={{ fontSize: 12.5, fontWeight: 600, color: stk.changeColor }}>{stk.change}</span>
                  </div>
                </div>
              ))}
              <div style={{ background: "#EEEDFD", borderRadius: 12, padding: "14px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, color: "#4640DE", fontWeight: 600 }}>Portfolio scanner found 3 breakouts</span>
                <Link to="/scanner" style={{ color: "#4640DE", fontSize: 13, fontWeight: 700 }}>View →</Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", background: "#14171F", padding: "18px 48px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          {INDICES.map((idx) => (
            <div key={idx.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ color: "#9297A8", fontSize: 13, fontWeight: 500 }}>{idx.name}</span>
              <span className="num" style={{ color: "white", fontSize: 14.5, fontWeight: 600 }}>{idx.value}</span>
              <span className="num" style={{ fontSize: 13, fontWeight: 600, color: idx.color }}>{idx.change}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", padding: "88px 48px", background: "#FAF9F6" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <div style={{ maxWidth: 560, marginBottom: 48 }}>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Everything in one place</span>
            <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.01em", marginTop: 10 }}>Five tools. One market view.</h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 20 }}>
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
              <p style={{ fontSize: 14, color: "#C9CCFB", lineHeight: 1.6, margin: 0 }}>Start with our free "Markets 101" course track — built for first-time SIP investors.</p>
              <span style={{ fontSize: 13.5, fontWeight: 700, color: "white" }}>Start learning →</span>
            </Link>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "8px 48px 88px", background: "#FAF9F6" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, padding: 48 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 40, flexWrap: "wrap" }}>
            <div style={{ maxWidth: 320 }}>
              <h2 style={{ fontSize: 28, fontWeight: 800 }}>Built for how Indian investors actually trade</h2>
              <p style={{ fontSize: 14.5, color: "#5B6270", lineHeight: 1.6, marginTop: 12 }}>Real NSE/BSE data, GMP tracking, and screeners tuned to Indian market structure — not a US product with rupee signs bolted on.</p>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 36, flex: 1 }}>
              {[["98.9%", "IPO GMP accuracy vs. listing day, last 40 IPOs"], ["< 200ms", "Exchange feed latency for NSE cash market data"], ["140+", "Video lessons across 6 course tracks"]].map(([n, l]) => (
                <div key={l}>
                  <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: 30, fontWeight: 800, color: "#4640DE" }}>{n}</span>
                  <p style={{ fontSize: 13.5, color: "#5B6270", marginTop: 6 }}>{l}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 48px 88px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <h2 style={{ fontSize: 30, fontWeight: 800, marginBottom: 32 }}>Trusted by investors across India</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 20 }}>
            {TESTIMONIALS.map((t) => (
              <div key={t.name} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
                <div style={{ display: "flex", gap: 3 }}>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <svg key={i} width="15" height="15" viewBox="0 0 16 16" fill="#F2A93B"><path d="M8 1l2.1 4.6 5 .5-3.8 3.4 1.1 5-4.4-2.6-4.4 2.6 1.1-5L1 6.1l5-.5L8 1z" /></svg>
                  ))}
                </div>
                <p style={{ fontSize: 14.5, color: "#33374A", lineHeight: 1.65, margin: 0 }}>"{t.quote}"</p>
                <div style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: 4 }}>
                  <div style={{ width: 36, height: 36, borderRadius: "50%", background: t.avatarBg, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 700, fontSize: 13 }}>{t.initials}</div>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: 13.5, fontWeight: 700 }}>{t.name}</span>
                    <span style={{ fontSize: 12, color: "#8A90A0" }}>{t.role}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 48px 88px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", background: "#14171F", borderRadius: 20, padding: "48px 56px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 40, flexWrap: "wrap" }}>
          <div style={{ maxWidth: 480, display: "flex", flexDirection: "column", gap: 12 }}>
            <span style={{ color: "#F2A93B", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Quantile Pro</span>
            <h2 style={{ color: "white", fontSize: 28, fontWeight: 800 }}>Unlock scanners, deep research &amp; live charts</h2>
            <p style={{ color: "#9297A8", fontSize: 14.5, lineHeight: 1.6, margin: 0 }}>Starting at ₹499/month. Cancel anytime. 7-day free trial on all paid plans.</p>
          </div>
          <Link to="/pricing" style={{ background: "#4640DE", color: "white", fontSize: 14.5, fontWeight: 700, padding: "14px 26px", borderRadius: 10, flexShrink: 0 }}>See plans &amp; pricing</Link>
        </div>
      </div>
    </>
  );
}
