import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

// Ported from templates/subscriber_dashboard.html. New GET /api/dashboard/
// bootstrap (app.py) replaces the fast synchronous part that used to be
// inline in subscriber_dashboard(); GET /api/dashboard/market-snapshot
// (already existed, unchanged) still supplies indices/sector-momentum/
// breadth/gainers/losers/shockers, fetched separately AFTER this page's
// own data loads — same "never block the page on slow S3/Dhan calls"
// design as the original.

const QUICK_NAV = [
  { label: "Live Chart", to: "/markets/chart", bg: "#EEEDFD", color: "#4640DE", icon: "chart" },
  { label: "Stock Research", to: "/markets/research", bg: "#E6F7F1", color: "#17A673", icon: "search" },
  { label: "IPO Hub", to: "/markets/ipo-hub", bg: "#FBF2E1", color: "#B98A2E", icon: "building" },
  { label: "Scanner", to: "/scanner", bg: "#FCEBEA", color: "#E0473F", icon: "target" },
  { label: "Education", to: "/education", bg: "#EEEDFD", color: "#4640DE", icon: "book" },
];

const QUICK_NAV_ICON_PATHS = {
  chart: <><path d="M3 13L7 8L10.5 11L15 5" /><path d="M11.5 5H15V8.5" /></>,
  search: <><circle cx="8" cy="8" r="5" /><path d="M15 15L11.5 11.5" /></>,
  building: <><path d="M4 15.5V4.5C4 3.7 4.7 3 5.5 3H10.5C11.3 3 12 3.7 12 4.5V15.5" /><path d="M12 8.5H13.5C14.3 8.5 15 9.2 15 10V15.5" /><path d="M2.5 15.5H15.5" /><path d="M6.5 6H8M6.5 9H8M6.5 12H8" /></>,
  target: <><circle cx="9" cy="9" r="6" /><circle cx="9" cy="9" r="2.6" /><path d="M9 1.5V4M9 14V16.5M1.5 9H4M14 9H16.5" /></>,
  book: <><path d="M3 4.2C3 3.5 3.6 3 4.3 3H8.5V15L4.3 14.7C3.6 14.6 3 14.1 3 13.4V4.2Z" /><path d="M15 4.2C15 3.5 14.4 3 13.7 3H9.5V15L13.7 14.7C14.4 14.6 15 14.1 15 13.4V4.2Z" /></>,
};

function numFmt(n) {
  return Number(n).toFixed(2);
}

function PctPill({ pct }) {
  const up = pct >= 0;
  return (
    <span className="num" style={{ fontSize: 11.5, fontWeight: 700, padding: "2px 7px", borderRadius: 999, background: up ? "#E6F7F1" : "#FCEBEA", color: up ? "#17A673" : "#E0473F" }}>
      {up ? "+" : ""}
      {numFmt(pct)}%
    </span>
  );
}

function StockRow({ stock, extraLabel }) {
  return (
    <div className="watchlist-row">
      <a className="symbol-link" href={`/markets/chart?symbol=${encodeURIComponent(stock.symbol)}`} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13.5, fontWeight: 700, color: "#14171F" }}>
        {stock.symbol}
      </a>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {extraLabel && <span style={{ fontSize: 11, color: "#8A90A0" }}>{extraLabel}</span>}
        <span className="num" style={{ fontSize: 13.5, fontWeight: 600 }}>₹{numFmt(stock.price)}</span>
        <PctPill pct={stock.changePct} />
      </div>
    </div>
  );
}

function StockList({ stocks, extraLabelFn }) {
  if (!stocks || !stocks.length) {
    return <p style={{ fontSize: 12.5, color: "#8A90A0", margin: 0, padding: "8px 0" }}>Data is temporarily unavailable.</p>;
  }
  return stocks.map((s) => <StockRow key={s.symbol} stock={s} extraLabel={extraLabelFn ? extraLabelFn(s) : null} />);
}

function linkifyAlertBody(text) {
  const parts = [];
  const re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = re.exec(text))) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push(
      <a key={key++} href={match[2]} target="_blank" rel="noopener noreferrer" className="notif-card-link">
        {match[1]}
      </a>
    );
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [bootstrapError, setBootstrapError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [watchlistTab, setWatchlistTab] = useState("rs");

  useEffect(() => {
    let cancelled = false;
    setBootstrapError(false);
    apiFetch("/api/dashboard/bootstrap")
      .then((res) => res.json())
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setBootstrapError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  // Deliberately started only after bootstrap resolves, not concurrently
  // with it — the market-snapshot fetch scans the full ~350-stock
  // watchlist and can take a while; firing it at the same time as the
  // (fast) bootstrap fetch doubled peak load on the same Dhan-quote lock
  // the two share and could leave the whole dashboard hung behind it.
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    apiFetch("/api/dashboard/market-snapshot")
      .then((res) => res.json())
      .then((res) => {
        if (!cancelled) setSnapshot(res);
      })
      .catch(() => {
        if (!cancelled) setSnapshot({});
      });
    return () => {
      cancelled = true;
    };
  }, [data]);

  if (bootstrapError) {
    return (
      <div style={{ width: "100%", padding: "80px 40px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>
          We couldn't load your dashboard right now. This is usually a temporary issue with live market data.
        </p>
        <button
          type="button"
          onClick={() => setRetryCount((c) => c + 1)}
          style={{ background: "#4640DE", color: "white", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "10px 20px", borderRadius: 9 }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || !user) {
    return (
      <div style={{ width: "100%", padding: "80px 40px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>
        Loading your dashboard…
      </div>
    );
  }

  const marketOpen = data.marketStatus.startsWith("Markets open");
  const planId = data.subscription.plan;
  const planBadgeStyle =
    planId === "premium"
      ? { background: "#F2A93B", color: "#14171F" }
      : planId === "pro"
      ? { background: "#4640DE", color: "white" }
      : { background: "rgba(255,255,255,0.1)", color: "#9297A8" };

  return (
    <div style={{ width: "100%", padding: "36px 40px 80px" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 26, flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800 }}>Welcome back, {user.name.split(" ")[0]}</h1>
            <p style={{ fontSize: 14, color: "#5B6270", marginTop: 4 }}>{data.today}</p>
          </div>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7, background: marketOpen ? "#E6F7F1" : "#F0F1F4", borderRadius: 999, padding: "7px 14px" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: marketOpen ? "#17A673" : "#8A90A0" }} />
            <span style={{ fontSize: 12.5, fontWeight: 700, color: marketOpen ? "#17A673" : "#5B6270" }}>{data.marketStatus}</span>
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 14 }}>
          {!snapshot ? (
            <div style={{ gridColumn: "1 / -1", fontSize: 12.5, color: "#8A90A0" }}>Loading market data…</div>
          ) : snapshot.indices && snapshot.indices.length ? (
            snapshot.indices.map((idx) => (
              <div key={idx.label} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 16 }}>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: "#8A90A0", textTransform: "uppercase", letterSpacing: "0.03em" }}>{idx.label}</span>
                <div className="num" style={{ fontSize: 19, fontWeight: 800, color: "#14171F", marginTop: 4 }}>{numFmt(idx.value)}</div>
                <div style={{ marginTop: 4 }}><PctPill pct={idx.changePct} /></div>
              </div>
            ))
          ) : (
            <div style={{ gridColumn: "1 / -1", fontSize: 12.5, color: "#8A90A0" }}>Market data is temporarily unavailable.</div>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginBottom: 24 }}>
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
            <span style={{ fontSize: 13, fontWeight: 700, display: "block", marginBottom: 12 }}>Market breadth</span>
            {!snapshot ? (
              <div style={{ fontSize: 12.5, color: "#8A90A0" }}>Loading…</div>
            ) : snapshot.breadth && snapshot.breadth.advancing != null ? (
              <>
                <div style={{ display: "flex", gap: 18 }}>
                  <div><span className="num" style={{ fontSize: 19, fontWeight: 800, color: "#17A673", display: "block" }}>{snapshot.breadth.advancing}</span><span style={{ fontSize: 11, color: "#8A90A0" }}>Advancing</span></div>
                  <div><span className="num" style={{ fontSize: 19, fontWeight: 800, color: "#E0473F", display: "block" }}>{snapshot.breadth.declining}</span><span style={{ fontSize: 11, color: "#8A90A0" }}>Declining</span></div>
                  <div><span className="num" style={{ fontSize: 19, fontWeight: 800, color: "#8A90A0", display: "block" }}>{snapshot.breadth.unchanged}</span><span style={{ fontSize: 11, color: "#8A90A0" }}>Unchanged</span></div>
                </div>
                <p style={{ fontSize: 10.5, color: "#8A90A0", margin: "10px 0 0" }}>Across {snapshot.breadth.sampleSize} tracked watchlist stocks.</p>
              </>
            ) : (
              <div style={{ fontSize: 12.5, color: "#8A90A0" }}>Breadth data is temporarily unavailable.</div>
            )}
          </div>

          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
            <span style={{ fontSize: 13, fontWeight: 700, display: "block", marginBottom: 12 }}>Sector momentum</span>
            {!snapshot ? (
              <div style={{ fontSize: 12.5, color: "#8A90A0" }}>Loading…</div>
            ) : snapshot.sectorMomentum && snapshot.sectorMomentum.length ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {snapshot.sectorMomentum.map((sec) => {
                  const up = sec.changePct >= 0;
                  return (
                    <span key={sec.label} className="num" style={{ fontSize: 12, fontWeight: 700, padding: "5px 10px", borderRadius: 999, background: up ? "#E6F7F1" : "#FCEBEA", color: up ? "#17A673" : "#E0473F" }}>
                      {sec.label} {up ? "+" : ""}{numFmt(sec.changePct)}%
                    </span>
                  );
                })}
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: "#8A90A0" }}>Sector data is temporarily unavailable.</div>
            )}
          </div>
        </div>

        {data.recentAlerts && data.recentAlerts.length > 0 && (
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>Today's alerts</span>
              <span style={{ fontSize: 11.5, color: "#8A90A0" }}>From your notification feed</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {data.recentAlerts.map((a, i) => (
                <div key={a.id || i}>
                  <div className="notif-card">
                    <div className="notif-card-icon">🔔</div>
                    <div className="notif-card-body">
                      <div className="notif-card-top">
                        <span className="notif-card-title">{a.title}</span>
                        <span className="notif-card-time">{a.sent_at.slice(0, 16).replace("T", " ")}</span>
                      </div>
                      <div className="notif-card-message">{linkifyAlertBody(a.body)}</div>
                    </div>
                  </div>
                  {i < data.recentAlerts.length - 1 && <div className="notif-card-divider" />}
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0,1fr))", gap: 14, marginBottom: 24 }}>
          {QUICK_NAV.map((q) => (
            <Link key={q.label} to={q.to} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 16, display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: q.bg, display: "flex", alignItems: "center", justifyContent: "center", color: q.color, flexShrink: 0 }}>
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7">
                  {QUICK_NAV_ICON_PATHS[q.icon]}
                </svg>
              </div>
              <span style={{ fontSize: 13.5, fontWeight: 700, color: "#14171F" }}>{q.label}</span>
            </Link>
          ))}
        </div>

        <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
          <div style={{ flex: 1.6, display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", gap: 2, background: "#F0F1F4", borderRadius: 9, padding: 3 }}>
                  {[["rs", "RS Rating"], ["gainers", "Gainers"], ["losers", "Losers"], ["shockers", "Volume Shockers"]].map(([key, label]) => (
                    <button key={key} type="button" className={"watchlist-tab-btn" + (watchlistTab === key ? " active" : "")} onClick={() => setWatchlistTab(key)}>
                      {label}
                    </button>
                  ))}
                </div>
                <Link to="/markets/chart-wall" style={{ fontSize: 12.5, fontWeight: 700, color: "#4640DE" }}>Manage →</Link>
              </div>

              {watchlistTab === "rs" && <StockList stocks={data.watchlist} />}
              {watchlistTab === "gainers" && (!snapshot ? <p style={{ fontSize: 12.5, color: "#8A90A0" }}>Loading…</p> : <StockList stocks={snapshot.topGainers} />)}
              {watchlistTab === "losers" && (!snapshot ? <p style={{ fontSize: 12.5, color: "#8A90A0" }}>Loading…</p> : <StockList stocks={snapshot.topLosers} />)}
              {watchlistTab === "shockers" &&
                (!snapshot ? (
                  <p style={{ fontSize: 12.5, color: "#8A90A0" }}>Loading…</p>
                ) : (
                  <StockList stocks={snapshot.volumeShockers} extraLabelFn={(s) => (s.volumeRatio ? `${numFmt(s.volumeRatio)}x avg vol` : "")} />
                ))}
            </div>

            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <span style={{ fontSize: 15, fontWeight: 700 }}>
                  EMA 10/20 Breakout{data.scanResults ? ` — as of ${data.scanResults.generated_at}` : ""}
                </span>
                <Link to="/scanner?id=dhan_ema_breakout" style={{ fontSize: 12.5, fontWeight: 700, color: "#4640DE" }}>Open scanner →</Link>
              </div>
              {data.scanResults && data.scanResults.rows && data.scanResults.rows.length ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 12 }}>
                  {data.scanResults.rows.map((s, i) => (
                    <div key={i} style={{ border: "1px solid #F0F1F4", borderRadius: 12, padding: 14 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, display: "block" }}>{s["Stock Name"]}</span>
                      <span className="num" style={{ fontSize: 12.5, color: "#5B6270" }}>
                        EPS {Math.trunc(s["EPS Strength"])} · PS {Math.trunc(s["Price Strength"])}
                      </span>
                      <span style={{ display: "inline-block", fontSize: 10.5, fontWeight: 700, color: "#4640DE", background: "#EEEDFD", padding: "2px 7px", borderRadius: 999, marginTop: 6 }}>
                        {s.Setup_Case}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ fontSize: 13, color: "#8A90A0", margin: 0, padding: "8px 0" }}>No scan run yet — run the EMA 10/20 Breakout scanner to see its latest matches here.</p>
              )}
            </div>
          </div>

          <div style={{ width: 340, flexShrink: 0, display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ background: "#14171F", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#F2A93B", letterSpacing: "0.04em", textTransform: "uppercase" }}>Your account</span>
                <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.03em", textTransform: "uppercase", padding: "4px 10px", borderRadius: 999, ...planBadgeStyle }}>
                  {data.subscription.plan_details.name} plan
                </span>
              </div>
              <span style={{ fontSize: 17, fontWeight: 800, color: "white", wordBreak: "break-all" }}>{user.email}</span>
              <div style={{ height: 1, background: "#2A2E3A", margin: "6px 0" }} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                <span style={{ color: "#9297A8" }}>Role</span>
                <span style={{ color: "white", fontWeight: 600, textTransform: "capitalize" }}>{user.role}</span>
              </div>
              {data.memberSince && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                  <span style={{ color: "#9297A8" }}>Member since</span>
                  <span style={{ color: "white", fontWeight: 600 }}>{data.memberSince}</span>
                </div>
              )}
              <Link to="/subscription" style={{ background: "rgba(255,255,255,0.08)", color: "white", textAlign: "center", fontSize: 13, fontWeight: 700, padding: "10px 0", borderRadius: 9, marginTop: 6 }}>
                Manage subscription →
              </Link>
            </div>

            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>Recommended courses</span>
                <Link to="/education" style={{ fontSize: 12, fontWeight: 700, color: "#4640DE" }}>All courses →</Link>
              </div>
              {(data.educationCourses || []).map((c) => (
                <Link key={c.title} to="/education" style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: "1px solid #F0F1F4" }}>
                  <div style={{ width: 40, height: 40, borderRadius: 9, background: c.bannerBg, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, display: "block", color: "#14171F" }}>{c.title}</span>
                    <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{c.lessons} lessons · {c.duration}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
