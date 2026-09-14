import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";

// Ported from templates/research.html. New GET /api/research (app.py)
// mirrors research()'s exact 4-connector orchestration and layered
// best-effort fallbacks — same flat data shape the Jinja template already
// consumed via simple truthiness checks (epsStrength/priceHistory/
// aiVerdict just absent when that best-effort step failed server-side).

const VERDICT_COLOR = { Strong: "#17A673", Mixed: "#B98A2E", Weak: "#E0473F" };
const PERIOD_LABELS = ["1M", "6M", "1Y", "3Y", "5Y"];

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function PriceChart({ priceHistory }) {
  const periods = priceHistory.periods;
  const available = PERIOD_LABELS.filter((l) => periods[l]);
  const [period, setPeriod] = useState(available.includes("1Y") ? "1Y" : available[0]);
  const p = periods[period];

  if (!p) return null;
  const up = p.endPrice >= p.startPrice;
  const color = up ? "#17A673" : "#E0473F";
  const pct = p.startPrice ? ((p.endPrice - p.startPrice) / p.startPrice) * 100 : 0;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {available.map((label) => (
            <button key={label} type="button" className={"pill-tab" + (label === period ? " active" : "")} onClick={() => setPeriod(label)}>
              {label}
            </button>
          ))}
        </div>
        <Link to="/markets/chart" style={{ fontSize: 12.5, color: "#4640DE", fontWeight: 700 }}>Open full chart →</Link>
      </div>
      <div style={{ fontSize: 13, color: "#5B6270", marginBottom: 8 }}>
        <span className="num" style={{ fontWeight: 700, color }}>
          {up ? "+" : ""}
          {pct.toFixed(1)}%
        </span>{" "}
        <span style={{ color: "#8A90A0" }}>
          ({fmtDate(p.startDate)} → {fmtDate(p.endDate)})
        </span>
      </div>
      <svg width="100%" height="180" viewBox="0 0 800 180" preserveAspectRatio="none">
        <polyline points={p.points} fill="none" stroke={color} strokeWidth="2.5" />
        <polygon points={`${p.points} 800,180 0,180`} fill={color} opacity="0.08" />
      </svg>
      <p style={{ fontSize: 11, color: "#B0B4C0", margin: "8px 0 0" }}>Daily closing price via screener.in.</p>
    </>
  );
}

export default function Research() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSymbol = searchParams.get("symbol") || "HDFCBANK";
  const [searchInput, setSearchInput] = useState(urlSymbol);
  const [data, setData] = useState(null);

  const sectionRefs = {
    overview: useRef(null),
    financials: useRef(null),
    ratios: useRef(null),
    quarterly: useRef(null),
    shareholding: useRef(null),
  };
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    setData(null);
    apiFetch(`/api/research?symbol=${encodeURIComponent(urlSymbol)}`)
      .then((res) => res.json())
      .then(setData);
  }, [urlSymbol]);

  useEffect(() => {
    function onKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.getElementById("stockSearchInput")?.select();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  function onSearchSubmit(e) {
    e.preventDefault();
    if (searchInput.trim()) setSearchParams({ symbol: searchInput.trim() });
  }

  function scrollToSection(key) {
    setActiveTab(key);
    sectionRefs[key].current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const symbol = urlSymbol;
  const sectionStyle = { scrollMarginTop: 96 };

  return (
    <>
      <div style={{ width: "100%", padding: "40px 48px 0" }}>
        <form
          onSubmit={onSearchSubmit}
          style={{ maxWidth: 1200, margin: "0 auto", display: "flex", alignItems: "center", gap: 14, background: "#FFFFFF", border: "1.5px solid #E3E6EC", borderRadius: 12, padding: "14px 20px" }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#8A90A0" strokeWidth="1.6">
            <circle cx="8" cy="8" r="6" />
            <path d="M12.5 12.5L16 16" />
          </svg>
          <input
            id="stockSearchInput"
            className="search-input"
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder='Search 2,100+ NSE / BSE stocks — try "HDFC Bank" or "TATASTEEL"'
            autoComplete="off"
          />
          <span style={{ fontSize: 12.5, color: "#C6C9D2", background: "#F0F1F4", padding: "4px 8px", borderRadius: 6, fontWeight: 600 }}>⌘K</span>
        </form>
      </div>

      {!data ? null : data.notFound ? (
        <div style={{ width: "100%", padding: "64px 48px" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>No match for "{symbol}"</h2>
            <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>
              We couldn't find that ticker on NSE/BSE. Try the exchange symbol without spaces — e.g. <strong>HDFCBANK</strong>, <strong>TATASTEEL</strong>, <strong>TCS</strong> or <strong>INFY</strong>.
            </p>
          </div>
        </div>
      ) : data.unavailable ? (
        <div style={{ width: "100%", padding: "64px 48px" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Live data temporarily unavailable</h2>
            <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach the data source for {symbol} just now. Please try again shortly.</p>
          </div>
        </div>
      ) : (
        <>
          <div style={{ width: "100%", padding: "20px 48px 0" }}>
            <div style={{ maxWidth: 1200, margin: "0 auto" }}>
              <div ref={sectionRefs.overview} style={{ ...sectionStyle, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: 28, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ display: "flex", gap: 16 }}>
                  <div style={{ width: 54, height: 54, borderRadius: 14, background: "#003D7A", display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 800, fontSize: 15 }}>
                    {data.header?.initials}
                  </div>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 22, fontWeight: 800, fontFamily: "'Manrope', sans-serif" }}>{data.header?.name}</span>
                      <span style={{ fontSize: 12, color: "#8A90A0", background: "#F0F1F4", padding: "3px 8px", borderRadius: 6, fontWeight: 600 }}>{symbol}</span>
                    </div>
                    <span style={{ fontSize: 13, color: "#8A90A0" }}>NSE, BSE</span>
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span className="num" style={{ fontSize: 30, fontWeight: 700, fontFamily: "'IBM Plex Mono', monospace" }}>{data.header?.price}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end", marginTop: 4 }}>
                    {data.header?.direction === "up" ? (
                      <>
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#17A673" strokeWidth="2"><path d="M2 8L6 4L10 8" /></svg>
                        <span className="num" style={{ color: "#17A673", fontWeight: 600, fontSize: 14.5 }}>+{data.header?.changePct} (last close)</span>
                      </>
                    ) : (
                      <>
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#E0473F" strokeWidth="2"><path d="M2 4L6 8L10 4" /></svg>
                        <span className="num" style={{ color: "#E0473F", fontWeight: 600, fontSize: 14.5 }}>-{data.header?.changePct} (last close)</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 22 }}>
                {[
                  ["overview", "Overview"], ["financials", "Financials"], ["ratios", "Ratios"],
                  ["quarterly", "Quarterly results"], ["shareholding", "Shareholding"],
                ].map(([key, label]) => (
                  <button key={key} type="button" className={"pill-tab" + (activeTab === key ? " active" : "")} onClick={() => scrollToSection(key)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div style={{ width: "100%", padding: "20px 48px 0" }}>
            <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", gap: 20, alignItems: "flex-start" }}>
              <div style={{ flex: 1.6, display: "flex", flexDirection: "column", gap: 18 }}>
                {data.aiVerdict && (
                  <div style={{ background: "#F1F0FD", border: "1px solid #DEDCFB", borderRadius: 18, padding: "22px 24px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#4640DE" }} />
                        <span style={{ fontSize: 12.5, fontWeight: 700, color: "#4640DE", letterSpacing: "0.02em" }}>AI Summary</span>
                      </div>
                      <span style={{ background: VERDICT_COLOR[data.aiVerdict.label], color: "white", fontSize: 11.5, fontWeight: 700, padding: "4px 11px", borderRadius: 100 }}>
                        {data.aiVerdict.label} fundamentals
                      </span>
                    </div>
                    <p style={{ fontSize: 14.5, color: "#33374A", lineHeight: 1.65, margin: 0 }}>{data.aiVerdict.summary}</p>
                    {data.aiVerdict.weaknesses?.length > 0 && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid #DEDCFB" }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#E0473F", display: "block", marginBottom: 6 }}>Weak points</span>
                        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#5B6270", lineHeight: 1.7 }}>
                          {data.aiVerdict.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                        </ul>
                      </div>
                    )}
                    <p style={{ fontSize: 11, color: "#8A90A0", margin: "12px 0 0" }}>AI-generated from the fundamentals on this page — not investment advice.</p>
                  </div>
                )}

                <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: 24 }}>
                  {data.priceHistory ? (
                    <PriceChart priceHistory={data.priceHistory} />
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 180, color: "#8A90A0", fontSize: 13.5 }}>
                      Chart unavailable right now — try again shortly.
                    </div>
                  )}
                </div>

                <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: 26 }}>
                  <h3 style={{ fontSize: 15.5, fontWeight: 700, marginBottom: 18 }}>Key ratios</h3>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: "22px 18px" }}>
                    {(data.fundamentals || []).map((f, i) => (
                      <div key={i}>
                        <span style={{ fontSize: 12, color: "#8A90A0", display: "block", marginBottom: 4 }}>{f.label}</span>
                        <span className="num" style={{ fontSize: 15, fontWeight: 700 }}>{f.value}</span>
                      </div>
                    ))}
                    {data.epsStrength && (
                      <div>
                        <span style={{ fontSize: 12, color: "#8A90A0", display: "block", marginBottom: 4 }}>EPS Strength</span>
                        <span className="num" style={{ fontSize: 15, fontWeight: 700, color: Number(data.epsStrength) >= 80 ? "#17A673" : Number(data.epsStrength) >= 50 ? "#B98A2E" : "#E0473F" }}>
                          {data.epsStrength}
                        </span>
                      </div>
                    )}
                    {data.priceStrength && (
                      <div>
                        <span style={{ fontSize: 12, color: "#8A90A0", display: "block", marginBottom: 4 }}>Price Strength</span>
                        <span className="num" style={{ fontSize: 15, fontWeight: 700, color: Number(data.priceStrength) >= 80 ? "#17A673" : Number(data.priceStrength) >= 50 ? "#B98A2E" : "#E0473F" }}>
                          {data.priceStrength}
                        </span>
                      </div>
                    )}
                  </div>
                  {(data.epsStrength || data.priceStrength) && (
                    <p style={{ fontSize: 11, color: "#B0B4C0", margin: "14px 0 0" }}>EPS Strength &amp; Price Strength via MarketSmith India, 1–99 scale.</p>
                  )}
                </div>

                <div ref={sectionRefs.financials} style={{ ...sectionStyle, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24 }}>
                  <span style={{ fontSize: 15, fontWeight: 700, display: "block", marginBottom: 14 }}>Profit &amp; loss (₹ Cr, standalone)</span>
                  <table>
                    <thead><tr><th>Particulars</th><th className="num">FY22</th><th className="num">FY23</th><th className="num">FY24</th><th className="num">FY25</th><th className="num">FY26E</th></tr></thead>
                    <tbody>
                      {(data.plRows || []).map((r, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: r.weight }}>{r.label}</td>
                          <td className="num">{r.fy22}</td>
                          <td className="num">{r.fy23}</td>
                          <td className="num">{r.fy24}</td>
                          <td className="num">{r.fy25}</td>
                          <td className="num" style={{ fontWeight: 700 }}>{r.fy26}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div style={{ display: "flex", gap: 18 }}>
                  <div style={{ flex: 1, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 12 }}>Balance sheet snapshot (FY25)</span>
                    {(data.balanceSheet || []).map((b, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderTop: "1px solid #F0F1F4" }}>
                        <span style={{ fontSize: 13, color: "#5B6270" }}>{b.label}</span>
                        <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>{b.value}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ flex: 1, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 12 }}>Cash flow snapshot (FY25)</span>
                    {(data.cashFlow || []).map((c, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderTop: "1px solid #F0F1F4" }}>
                        <span style={{ fontSize: 13, color: "#5B6270" }}>{c.label}</span>
                        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: c.color }}>{c.value}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div ref={sectionRefs.quarterly} style={{ ...sectionStyle, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24 }}>
                  <span style={{ fontSize: 15, fontWeight: 700, display: "block", marginBottom: 14 }}>Quarterly results (₹ Cr)</span>
                  <table>
                    <thead><tr><th>Quarter</th><th className="num">Revenue</th><th className="num">Net Profit</th><th className="num">EPS (₹)</th><th className="num">YoY</th></tr></thead>
                    <tbody>
                      {(data.quarters || []).map((q, i) => (
                        <tr key={i}>
                          <td>{q.label}</td>
                          <td className="num">{q.revenue}</td>
                          <td className="num">{q.profit}</td>
                          <td className="num">{q.eps}</td>
                          <td className="num" style={{ fontWeight: 700, color: q.yoyColor }}>{q.yoy}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ width: 320, display: "flex", flexDirection: "column", gap: 18, flexShrink: 0 }}>
                <div style={{ background: "#14171F", borderRadius: 18, padding: 22, display: "flex", flexDirection: "column", gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "white" }}>Add to watchlist</span>
                  <p style={{ fontSize: 12.5, color: "#9297A8", lineHeight: 1.6, margin: 0 }}>Get price alerts and daily fundamentals digest for {symbol}.</p>
                  <div style={{ background: "#4640DE", color: "white", fontSize: 13, fontWeight: 700, padding: "10px 0", borderRadius: 8, textAlign: "center", marginTop: 4 }}>+ Add stock</div>
                </div>

                <div ref={sectionRefs.ratios} style={{ ...sectionStyle, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 16 }}>5-year ratio trend</span>
                  {(data.ratios || []).map((r, i) => (
                    <div key={i} style={{ marginBottom: 16 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 12.5, color: "#5B6270" }}>{r.label}</span>
                        <span className="num" style={{ fontSize: 12.5, fontWeight: 700 }}>{r.current}</span>
                      </div>
                      <svg width="100%" height="32" viewBox="0 0 260 32" preserveAspectRatio="none">
                        <polyline points={r.points} fill="none" stroke="#4640DE" strokeWidth="2" />
                      </svg>
                    </div>
                  ))}
                </div>

                <div ref={sectionRefs.shareholding} style={{ ...sectionStyle, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Shareholding pattern</span>
                  <div style={{ width: "100%", height: 10, borderRadius: 100, overflow: "hidden", display: "flex", marginBottom: 14 }}>
                    {(data.shareholding || []).map((s, i) => (
                      <div key={i} style={{ width: s.pct, background: s.color }} />
                    ))}
                  </div>
                  {(data.shareholding || []).map((s, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ width: 9, height: 9, borderRadius: 3, background: s.color, display: "inline-block" }} />
                        <span style={{ fontSize: 12.5, color: "#5B6270" }}>{s.label}</span>
                      </div>
                      <span className="num" style={{ fontSize: 12.5, fontWeight: 700 }}>{s.pct}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      <div style={{ height: 88 }} />
    </>
  );
}
