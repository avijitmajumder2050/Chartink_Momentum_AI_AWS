// Ported from templates/vision.html. Static-in-React, same reasoning as
// the other marketing pages — mock_data.py's vision_data() is
// illustrative company-story copy, not real data.
const VALUES = [
  { num: "01", title: "Radical transparency", desc: 'Every score and screener criterion is documented — no black-box "buy signals."' },
  { num: "02", title: "India-first design", desc: "Built around NSE/BSE market structure, circuit limits and settlement cycles." },
  { num: "03", title: "Education over hype", desc: 'We teach the "why" behind every metric, not just a green or red signal.' },
  { num: "04", title: "Accessible pricing", desc: "A serious research stack should cost less than a weekly food delivery order." },
];
const TIMELINE = [
  { year: "2022", title: "Quantile founded in Mumbai", desc: "Three engineers and a chartered accountant, frustrated by scattered IPO data." },
  { year: "2023", title: "IPO Hub & GMP tracking launch", desc: "Real-time grey market premium tracking across 60+ IPOs in the first year." },
  { year: "2024", title: "Crossed 5 lakh investors", desc: 'Stock Research and the first course track, "Markets 101," go live.' },
  { year: "2025", title: "Scanner & live charting launch", desc: "Full technical screener with 40+ filters and multi-timeframe charts." },
  { year: "2026", title: "12.4 lakh investors and counting", desc: "Education platform expands to 6 course tracks and live weekly webinars." },
];
const STATS = [
  ["12.4L+", "registered investors"],
  ["2,100+", "NSE/BSE stocks tracked"],
  ["₹48,600 Cr", "portfolio value monitored"],
  ["18", "cities with Quantile meet-ups"],
];

export default function Vision() {
  return (
    <>
      <div style={{ width: "100%", padding: "76px clamp(16px, 5vw, 48px) 56px", textAlign: "center" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 18, alignItems: "center" }}>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Our vision</span>
          <h1 style={{ fontSize: 44, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1.15 }}>A financially confident India, one investor at a time.</h1>
          <p style={{ fontSize: 17, color: "#5B6270", lineHeight: 1.65, margin: 0 }}>
            We started Quantile because good market data was either locked behind broker terminals or scattered across a dozen unreliable Telegram channels. We think every Indian investor deserves better tools — and the education to use them well.
          </p>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 clamp(16px, 5vw, 48px) 72px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: 34, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: "#EEEDFD", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#4640DE" strokeWidth="1.7"><circle cx="10" cy="10" r="7" /><path d="M10 6v4l3 2" /></svg>
            </div>
            <h2 style={{ fontSize: 21, fontWeight: 700 }}>Our mission</h2>
            <p style={{ fontSize: 14.5, color: "#5B6270", lineHeight: 1.7, margin: 0 }}>Give every retail investor in India institutional-grade market data, screening tools and structured education — in one subscription, in plain language, without jargon or paywalled half-truths.</p>
          </div>
          <div style={{ background: "#14171F", borderRadius: 18, padding: 34, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: "rgba(255,255,255,0.08)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#F2A93B" strokeWidth="1.7"><path d="M2 10c2-4 5-6 8-6s6 2 8 6c-2 4-5 6-8 6s-6-2-8-6z" /><circle cx="10" cy="10" r="2.4" /></svg>
            </div>
            <h2 style={{ fontSize: 21, fontWeight: 700, color: "white" }}>Our vision</h2>
            <p style={{ fontSize: 14.5, color: "#9297A8", lineHeight: 1.7, margin: 0 }}>A decade from now, "I don't understand the stock market" is no longer a reason Indians stay out of it. We want to be the default place a new investor opens before their first trade — and the tool a serious one never turns off.</p>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 clamp(16px, 5vw, 48px) 80px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 32 }}>What we stand for</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 20 }}>
            {VALUES.map((v) => (
              <div key={v.num} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <span style={{ fontFamily: "'Manrope', sans-serif", fontWeight: 800, fontSize: 26, color: "#D8DAE3" }}>{v.num}</span>
                <h3 style={{ fontSize: 16.5, fontWeight: 700 }}>{v.title}</h3>
                <p style={{ fontSize: 13.5, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>{v.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 clamp(16px, 5vw, 48px) 80px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 20, padding: "40px clamp(16px, 5vw, 48px)", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 24 }}>
          {STATS.map(([n, l]) => (
            <div key={l} style={{ textAlign: "center" }}>
              <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: 28, fontWeight: 800, color: "#4640DE" }}>{n}</span>
              <p style={{ fontSize: 13, color: "#5B6270", marginTop: 6 }}>{l}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", padding: "0 clamp(16px, 5vw, 48px) 90px" }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 40, textAlign: "center" }}>How we got here</h2>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {TIMELINE.map((t, i) => (
              <div key={t.year} style={{ display: "flex", gap: 24 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 80, flexShrink: 0 }}>
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, fontSize: 14, color: "#4640DE" }}>{t.year}</span>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#4640DE", margin: "8px 0" }} />
                  {i < TIMELINE.length - 1 && <div style={{ width: 1.5, flex: 1, background: "#E3E6EC", minHeight: 40 }} />}
                </div>
                <div style={{ paddingBottom: 32 }}>
                  <h3 style={{ fontSize: 16.5, fontWeight: 700 }}>{t.title}</h3>
                  <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, marginTop: 4, maxWidth: 560 }}>{t.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
