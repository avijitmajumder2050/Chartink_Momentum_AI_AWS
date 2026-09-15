import { Link } from "react-router-dom";

// Ported from templates/education.html. Static-in-React, same reasoning
// as Home/Capabilities — mock_data.py's education_data() is illustrative
// marketing content, not real course-platform data.
const COURSES = [
  { title: "Markets 101: Your First Trade", level: "Beginner", levelColor: "#17A673", levelBg: "#E6F7F1", desc: "Demat accounts, order types and how NSE/BSE settlement actually works.", lessons: 18, duration: "3h 20m", cta: "Start free", bannerBg: "#4640DE" },
  { title: "Reading a Balance Sheet", level: "Beginner", levelColor: "#17A673", levelBg: "#E6F7F1", desc: "P/E, ROE and debt ratios explained with real Indian company filings.", lessons: 16, duration: "2h 55m", cta: "Start free", bannerBg: "#17A673" },
  { title: "Technical Analysis Foundations", level: "Intermediate", levelColor: "#B98A2E", levelBg: "#FBF2E1", desc: "Candlestick patterns, support/resistance and moving averages in practice.", lessons: 24, duration: "6h 40m", cta: "View course", bannerBg: "#B98A2E" },
  { title: "IPO Investing Playbook", level: "Intermediate", levelColor: "#B98A2E", levelBg: "#FBF2E1", desc: "How to read a DRHP, judge GMP signals and size an application.", lessons: 12, duration: "2h 10m", cta: "View course", bannerBg: "#4640DE" },
  { title: "Options Strategy Lab", level: "Advanced", levelColor: "#E0473F", levelBg: "#FCEBEA", desc: "Covered calls, spreads and hedging with NIFTY & Bank NIFTY options.", lessons: 30, duration: "8h 15m", cta: "View course", bannerBg: "#14171F" },
  { title: "Building a Screener Strategy", level: "Advanced", levelColor: "#E0473F", levelBg: "#FCEBEA", desc: "Turn a trading thesis into a repeatable Quantile scanner query.", lessons: 14, duration: "3h 45m", cta: "View course", bannerBg: "#17A673" },
];
const CURRICULUM = [
  { num: "01", title: "Why price action matters more than news", duration: "18 min" },
  { num: "02", title: "Candlestick anatomy and core patterns", duration: "32 min" },
  { num: "03", title: "Support, resistance and trendlines", duration: "27 min" },
  { num: "04", title: "Moving averages and crossovers", duration: "24 min" },
  { num: "05", title: "RSI, MACD and applying them in Scanner", duration: "35 min" },
];
const WEBINARS = [
  { tag: "LIVE Thu, 6 PM", tagColor: "#E0473F", tagBg: "#FCEBEA", date: "22 Aug", title: "Reading GMP signals ahead of the festive IPO season", host: "Rhea Kapoor, Research Lead", seats: "340 registered" },
  { tag: "Upcoming", tagColor: "#4640DE", tagBg: "#EEEDFD", date: "27 Aug", title: "Building your first scanner-based watchlist", host: "CA Meera Rangan", seats: "128 registered" },
  { tag: "Upcoming", tagColor: "#4640DE", tagBg: "#EEEDFD", date: "2 Sep", title: "Bank NIFTY options: a beginner-safe framework", host: "Arjun Nair, Derivatives Analyst", seats: "96 registered" },
];

export default function Education() {
  return (
    <>
      <div style={{ width: "100%", padding: "56px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
          <div>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Education</span>
            <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>Learn to invest, one track at a time</h1>
            <p style={{ fontSize: 15, color: "#5B6270", marginTop: 8, maxWidth: 520 }}>140+ video lessons across 6 tracks, from your first demat account to options strategy.</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "white", background: "#14171F", padding: "9px 16px", borderRadius: 9 }}>All levels</span>
            {["Beginner", "Intermediate", "Advanced"].map((l) => (
              <span key={l} style={{ fontSize: 13, fontWeight: 600, color: "#5B6270", padding: "9px 16px" }}>{l}</span>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "28px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          {COURSES.map((c) => (
            <div key={c.title} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              <div style={{ height: 110, background: c.bannerBg, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="34" height="34" viewBox="0 0 34 34" fill="none" stroke="white" strokeWidth="1.6" opacity="0.9"><rect x="4" y="7" width="26" height="20" rx="2" /><path d="M13 13l8 4-8 4z" fill="white" stroke="none" /></svg>
              </div>
              <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: c.levelColor, background: c.levelBg, padding: "4px 9px", borderRadius: 100, width: "fit-content" }}>{c.level}</span>
                <h3 style={{ fontSize: 16.5, fontWeight: 700, lineHeight: 1.3 }}>{c.title}</h3>
                <p style={{ fontSize: 13, color: "#5B6270", lineHeight: 1.6, margin: 0, flex: 1 }}>{c.desc}</p>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 8, borderTop: "1px solid #F0F1F4" }}>
                  <span style={{ fontSize: 12, color: "#8A90A0" }}>{c.lessons} lessons · {c.duration}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#4640DE" }}>{c.cta}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", padding: "64px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 18 }}>Course detail — Technical Analysis Foundations</h2>
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: 36, display: "flex", gap: 44, flexWrap: "wrap" }}>
            <div style={{ flex: 1.2, minWidth: 280, display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: "#B98A2E", background: "#FBF2E1", padding: "4px 9px", borderRadius: 100 }}>Intermediate</span>
                <h3 style={{ fontSize: 24, fontWeight: 800, marginTop: 12 }}>Technical Analysis Foundations</h3>
                <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.7, marginTop: 8 }}>Learn to read candlestick patterns, support &amp; resistance, moving averages and RSI — then apply them directly inside the Quantile scanner and chart tools.</p>
              </div>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                {[["Lessons", "24 videos"], ["Duration", "6h 40m"], ["Instructor", "CA Meera Rangan"], ["Rating", "4.8 (2,340)"]].map(([l, v]) => (
                  <div key={l}><span style={{ fontSize: 11.5, color: "#8A90A0", display: "block" }}>{l}</span><span style={{ fontSize: 14, fontWeight: 700 }}>{v}</span></div>
                ))}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                <span style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 6 }}>Curriculum</span>
                {CURRICULUM.map((m) => (
                  <div key={m.num} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "11px 0", borderTop: "1px solid #F0F1F4" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 12, color: "#B0B4C0", width: 18 }}>{m.num}</span>
                      <span style={{ fontSize: 13.5, fontWeight: 500 }}>{m.title}</span>
                    </div>
                    <span style={{ fontSize: 12, color: "#8A90A0" }}>{m.duration}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ width: 300, flexShrink: 0 }}>
              <div style={{ background: "#FAF9F6", border: "1px solid #E3E6EC", borderRadius: 14, padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
                <span style={{ fontSize: 22, fontWeight: 800, fontFamily: "'Manrope', sans-serif" }}>Included in Pro</span>
                <p style={{ fontSize: 12.5, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>Free with any paid Quantile subscription. Also purchasable standalone for ₹1,499.</p>
                <Link to="/pricing" style={{ background: "#4640DE", color: "white", textAlign: "center", fontSize: 14, fontWeight: 700, padding: "13px 0", borderRadius: 10 }}>Enroll now</Link>
                <div style={{ textAlign: "center", fontSize: 12.5, color: "#4640DE", fontWeight: 600 }}>Preview first lesson free</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "64px clamp(16px, 5vw, 48px) 88px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
            <h2 style={{ fontSize: 24, fontWeight: 800 }}>Live &amp; upcoming webinars</h2>
            <span style={{ fontSize: 13.5, fontWeight: 700, color: "#4640DE" }}>View full calendar →</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
            {WEBINARS.map((w) => (
              <div key={w.title} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: w.tagColor, background: w.tagBg, padding: "4px 9px", borderRadius: 100 }}>{w.tag}</span>
                  <span style={{ fontSize: 12, color: "#8A90A0" }}>{w.date}</span>
                </div>
                <h3 style={{ fontSize: 15.5, fontWeight: 700, lineHeight: 1.35 }}>{w.title}</h3>
                <span style={{ fontSize: 12.5, color: "#5B6270" }}>with {w.host}</span>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 8, borderTop: "1px solid #F0F1F4", marginTop: 4 }}>
                  <span style={{ fontSize: 12, color: "#8A90A0" }}>{w.seats}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#4640DE" }}>Reserve seat →</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
