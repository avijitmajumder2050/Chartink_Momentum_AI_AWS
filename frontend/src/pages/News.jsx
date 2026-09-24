import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

// GET /api/news (app.py -> connectors/news_connector.py): publisher RSS
// feeds, a Google News order-win search, and BSE/NSE order-win filings,
// each cached server-side for 2-3 minutes — so polling every minute here
// keeps the page close to live without hammering any source.
const REFRESH_MS = 60 * 1000;
const PAGE_STEP = 20;

const TABS = [
  { key: "ALL", label: "All" },
  { key: "ORDER WIN", label: "Order Wins" },
  { key: "MARKETS", label: "Markets" },
  { key: "CORPORATE", label: "Corporate" },
  { key: "IPO", label: "IPO" },
  { key: "ECONOMY", label: "Economy" },
  { key: "GLOBAL", label: "Global" },
];

function timeAgo(iso, now) {
  if (!iso) return "";
  const seconds = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Opens the source article/filing in a new tab; plain text if no link.
function Headline({ href, style, children }) {
  if (!href) return <span style={style}>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{ ...style, color: "inherit", textDecoration: "none" }}>
      {children}
    </a>
  );
}

function ValueChip({ value }) {
  if (!value) return null;
  return <span style={{ fontSize: 11.5, fontWeight: 800, color: "#17A673", background: "#E6F7F1", padding: "3px 8px", borderRadius: 100, whiteSpace: "nowrap" }}>{value}</span>;
}

function SourceBadge({ source }) {
  const official = source === "BSE filing" || source === "NSE filing";
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color: official ? "#4640DE" : "#8A90A0", background: official ? "#EEEDFD" : "transparent", padding: official ? "2px 7px" : 0, borderRadius: 100 }}>
      {official ? `Official · ${source}` : source}
    </span>
  );
}

function OrderWinRow({ w, now, compact }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, padding: compact ? "10px 0" : 18, borderTop: compact ? "1px solid #F0F1F4" : "none" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {(w.symbol || w.company) && <span style={{ fontSize: 12.5, fontWeight: 800 }}>{w.symbol || w.company}</span>}
        <ValueChip value={w.orderValue} />
        <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{timeAgo(w.publishedAt, now)}</span>
      </div>
      <Headline href={w.link} style={{ fontSize: compact ? 13 : 15, fontWeight: compact ? 600 : 700, lineHeight: 1.4 }}>
        {w.headline}
      </Headline>
      <SourceBadge source={w.source} />
    </div>
  );
}

export default function News() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("ALL");
  const [shown, setShown] = useState(PAGE_STEP);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = () => {
      apiFetch("/api/news")
        .then((res) => res.json())
        .then((d) => !cancelled && setData(d))
        // keep showing the last good data if a background refresh fails
        .catch(() => !cancelled && setData((prev) => prev || { unavailable: true }))
        .finally(() => {
          if (!cancelled) timer = setTimeout(load, REFRESH_MS);
        });
    };
    load();
    const tick = setInterval(() => setNow(Date.now()), 30 * 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(tick);
    };
  }, []);

  if (!data) return null;

  const { stories = [], orderWins = [], trending = [], gainers = [], losers = [], unavailable, updatedAt, moversUpdatedAt } = data;
  const filtered = tab === "ALL" ? stories : stories.filter((s) => s.tag === tab);
  const featured = tab === "ALL" ? filtered[0] : null;
  const list = (featured ? filtered.slice(1) : filtered).slice(0, shown);
  const remaining = (featured ? filtered.length - 1 : filtered.length) - list.length;

  const selectTab = (key) => {
    setTab(key);
    setShown(PAGE_STEP);
  };

  return (
    <>
      <style>{"@keyframes newsLivePulse{0%,100%{opacity:1}50%{opacity:.35}} .news-live-dot{animation:newsLivePulse 1.6s ease-in-out infinite} @media (prefers-reduced-motion: reduce){.news-live-dot{animation:none}}"}</style>
      <div style={{ width: "100%", padding: "clamp(16px, 5vw, 48px) clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 16, justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>News</span>
              {!unavailable && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: "#17A673" }}>
                  <span className="news-live-dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "#17A673" }} />
                  Live · updated {timeAgo(updatedAt, now)}
                </span>
              )}
            </div>
            <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>Markets news &amp; analysis</h1>
          </div>
          <div style={{ display: "flex", gap: 6, overflowX: "auto", maxWidth: "100%", WebkitOverflowScrolling: "touch" }}>
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => selectTab(key)}
                style={{
                  fontFamily: "inherit", fontSize: 13, fontWeight: tab === key ? 700 : 600, border: "none", cursor: "pointer", whiteSpace: "nowrap",
                  color: tab === key ? "white" : "#5B6270", background: tab === key ? "#14171F" : "transparent", padding: "9px 16px", borderRadius: 9,
                }}
              >
                {label}
                {key === "ORDER WIN" && orderWins.length > 0 && (
                  <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 800, color: tab === key ? "#14171F" : "white", background: tab === key ? "white" : "#17A673", padding: "1px 6px", borderRadius: 100 }}>{orderWins.length}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "28px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
          <div style={{ flex: "1.7 1 300px", minWidth: 0, display: "flex", flexDirection: "column", gap: 18 }}>
            {unavailable ? (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "clamp(16px, 5vw, 48px) 36px", textAlign: "center" }}>
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>News feed temporarily unavailable</h2>
                <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach any of our news sources just now. Please try again shortly.</p>
              </div>
            ) : tab === "ORDER WIN" ? (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
                <div style={{ padding: "16px 18px", borderBottom: "1px solid #E3E6EC" }}>
                  <span style={{ fontSize: 15, fontWeight: 800 }}>Order wins — last 3 days</span>
                  <p style={{ fontSize: 12.5, color: "#5B6270", margin: "4px 0 0" }}>Company announcements of new orders and contracts, from BSE/NSE filings and market news. Official filings link to the company's own disclosure.</p>
                </div>
                {!orderWins.length ? (
                  <p style={{ padding: 30, textAlign: "center", fontSize: 13, color: "#8A90A0", margin: 0 }}>No order wins reported in the last 3 days.</p>
                ) : (
                  orderWins.map((w, i) => (
                    <div key={`${w.link}-${i}`} style={{ borderTop: i ? "1px solid #F0F1F4" : "none" }}>
                      <OrderWinRow w={w} now={now} />
                    </div>
                  ))
                )}
              </div>
            ) : (
              <>
                {featured && (
                  <div style={{ background: "#14171F", borderRadius: 18, padding: 32, display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: "#14171F", background: "#F2A93B", padding: "4px 10px", borderRadius: 100 }}>{featured.tag}</span>
                      <span style={{ fontSize: 12, color: "#9297A8" }}>{timeAgo(featured.publishedAt, now)} · {featured.source}</span>
                    </div>
                    <Headline href={featured.link} style={{ fontSize: 26, fontWeight: 800, color: "white", lineHeight: 1.3, maxWidth: 720 }}>
                      <span style={{ color: "white" }}>{featured.headline}</span>
                    </Headline>
                  </div>
                )}
                {!list.length && !featured && (
                  <p style={{ padding: 30, textAlign: "center", fontSize: 13, color: "#8A90A0", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, margin: 0 }}>No stories in this category right now.</p>
                )}
                {list.map((s, i) => (
                  <div key={`${s.link}-${i}`} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 20, display: "flex", gap: 18, alignItems: "center" }}>
                    <div style={{ width: 88, height: 68, borderRadius: 10, background: s.thumbBg, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: s.tagColor, background: s.tagBg, padding: "3px 8px", borderRadius: 100 }}>{s.tag}</span>
                        <ValueChip value={s.orderValue} />
                        <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{timeAgo(s.publishedAt, now)}</span>
                      </div>
                      <Headline href={s.link} style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.35 }}>
                        {s.headline}
                      </Headline>
                      <span style={{ fontSize: 12.5, color: "#8A90A0" }}>{s.source}</span>
                    </div>
                  </div>
                ))}
                {remaining > 0 && (
                  <button
                    type="button"
                    onClick={() => setShown((n) => n + PAGE_STEP)}
                    style={{ alignSelf: "center", fontFamily: "inherit", fontSize: 13, fontWeight: 700, color: "#14171F", background: "#FFFFFF", border: "1px solid #E3E6EC", cursor: "pointer", padding: "10px 22px", borderRadius: 9 }}
                  >
                    Show more ({remaining})
                  </button>
                )}
              </>
            )}
          </div>

          <div style={{ width: "min(320px, 100%)", flex: "1 0 260px", display: "flex", flexDirection: "column", gap: 18 }}>
            {tab !== "ORDER WIN" && orderWins.length > 0 && (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>Latest order wins</span>
                  <button type="button" onClick={() => selectTab("ORDER WIN")} style={{ fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, color: "#4640DE", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                    See all ›
                  </button>
                </div>
                {orderWins.slice(0, 5).map((w, i) => (
                  <OrderWinRow key={`${w.link}-${i}`} w={w} now={now} compact />
                ))}
              </div>
            )}

            {trending.length > 0 && (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Trending now</span>
                {trending.map((t, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 12, padding: "10px 0", borderTop: "1px solid #F0F1F4" }}>
                    <span className="num" style={{ fontSize: 15, fontWeight: 700, color: "#D8DAE3" }}>{t.rank}</span>
                    <Headline href={t.link} style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>
                      {t.headline}
                    </Headline>
                  </div>
                ))}
              </div>
            )}

            {(gainers.length > 0 || losers.length > 0) && (
              <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
                <span style={{ fontSize: 14, fontWeight: 700, display: "block" }}>Market movers</span>
                <span style={{ fontSize: 11.5, color: "#8A90A0", display: "block", marginBottom: 14 }}>Tracked watchlist · as of {timeAgo(moversUpdatedAt, now)}</span>
                {gainers.length > 0 && (
                  <>
                    <span style={{ fontSize: 11.5, color: "#8A90A0", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Top gainers</span>
                    {gainers.map((g) => (
                      <div key={g.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: "1px solid #F0F1F4" }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{g.symbol}</span>
                        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: "#17A673" }}>{g.change}</span>
                      </div>
                    ))}
                  </>
                )}
                {losers.length > 0 && (
                  <>
                    <span style={{ fontSize: 11.5, color: "#8A90A0", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 10, display: "block" }}>Top losers</span>
                    {losers.map((l) => (
                      <div key={l.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: "1px solid #F0F1F4" }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{l.symbol}</span>
                        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: "#E0473F" }}>{l.change}</span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

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
