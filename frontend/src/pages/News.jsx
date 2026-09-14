import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

// Ported from templates/news.html. New GET /api/news (app.py) mirrors
// the news() route's logic exactly (RSS feed + mock gainers/losers,
// same fallback-to-unavailable on failure).
export default function News() {
  const [data, setData] = useState(null);

  useEffect(() => {
    apiFetch("/api/news")
      .then((res) => res.json())
      .then(setData)
      .catch(() => setData({ unavailable: true }));
  }, []);

  if (!data) return null;

  const { stories = [], trending = [], gainers = [], losers = [], unavailable } = data;
  const featured = stories[0];
  const rest = stories.slice(1);

  return (
    <>
      <div style={{ width: "100%", padding: "48px 48px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>News</span>
            <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>Markets news &amp; analysis</h1>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "white", background: "#14171F", padding: "9px 16px", borderRadius: 9 }}>All</span>
            {["Markets", "IPO", "Economy", "Corporate", "Global"].map((label) => (
              <span key={label} style={{ fontSize: 13, fontWeight: 600, color: "#5B6270", padding: "9px 16px" }}>{label}</span>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "28px 48px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", gap: 24, alignItems: "flex-start" }}>
          <div style={{ flex: 1.7, display: "flex", flexDirection: "column", gap: 18 }}>
            {unavailable ? (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px", textAlign: "center" }}>
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>News feed temporarily unavailable</h2>
                <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach any of our news sources just now. Please try again shortly.</p>
              </div>
            ) : (
              <>
                {featured && (
                  <div style={{ background: "#14171F", borderRadius: 18, padding: 32, display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: "#14171F", background: "#F2A93B", padding: "4px 10px", borderRadius: 100 }}>{featured.tag}</span>
                      <span style={{ fontSize: 12, color: "#9297A8" }}>{featured.time} · {featured.source}</span>
                    </div>
                    <h2 style={{ fontSize: 26, fontWeight: 800, color: "white", lineHeight: 1.3, maxWidth: 720 }}>{featured.headline}</h2>
                  </div>
                )}
                {rest.map((s, i) => (
                  <div key={i} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 20, display: "flex", gap: 18, alignItems: "center" }}>
                    <div style={{ width: 88, height: 68, borderRadius: 10, background: s.thumbBg, flexShrink: 0 }} />
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: s.tagColor, background: s.tagBg, padding: "3px 8px", borderRadius: 100 }}>{s.tag}</span>
                        <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{s.time}</span>
                      </div>
                      <span style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.35 }}>{s.headline}</span>
                      <span style={{ fontSize: 12.5, color: "#8A90A0" }}>{s.source}</span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>

          <div style={{ width: 320, flexShrink: 0, display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
              <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Trending now</span>
              {trending.map((t, i) => (
                <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 12, padding: "10px 0", borderTop: "1px solid #F0F1F4" }}>
                  <span className="num" style={{ fontSize: 15, fontWeight: 700, color: "#D8DAE3" }}>{t.rank}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>{t.headline}</span>
                </div>
              ))}
            </div>

            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
              <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Market movers</span>
              <span style={{ fontSize: 11.5, color: "#8A90A0", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Top gainers</span>
              {gainers.map((g, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: "1px solid #F0F1F4" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{g.symbol}</span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 700, color: "#17A673" }}>{g.change}</span>
                </div>
              ))}
              <span style={{ fontSize: 11.5, color: "#8A90A0", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 10, display: "block" }}>Top losers</span>
              {losers.map((l, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: "1px solid #F0F1F4" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{l.symbol}</span>
                  <span className="num" style={{ fontSize: 13, fontWeight: 700, color: "#E0473F" }}>{l.change}</span>
                </div>
              ))}
            </div>

            <div style={{ background: "#14171F", borderRadius: 16, padding: 22, display: "flex", flexDirection: "column", gap: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "white" }}>Never miss a market-moving story</span>
              <p style={{ fontSize: 12.5, color: "#9297A8", lineHeight: 1.6, margin: 0 }}>Get a 7 AM digest of overnight global cues and today's key levels.</p>
              <div style={{ background: "#4640DE", color: "white", textAlign: "center", fontSize: 13, fontWeight: 700, padding: "10px 0", borderRadius: 8, marginTop: 4 }}>Subscribe to digest</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ height: 88 }} />
    </>
  );
}
