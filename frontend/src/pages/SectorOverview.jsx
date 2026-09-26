import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import SectorDayView from "./SectorDayView";

const VIEWS = [
  { key: "day", label: "Day view" },
  { key: "screen", label: "Investment screen" },
];

// GET /api/markets/sectors (app.py -> connectors/sector_connector.py):
// every index in S3's uploads/sector_indices.csv with its 200-day EMA,
// daily RSI(14) and the investment-eligible screen. The rule's numbers
// come from the API (data.rule) so the copy here can't drift from it.
const REFRESH_MS = 2 * 60 * 1000;

const FILTERS = [
  { key: "all", label: "All" },
  { key: "eligible", label: "Eligible" },
  { key: "Broad market", label: "Broad market" },
  { key: "Sector", label: "Sectors" },
  { key: "Thematic", label: "Thematic" },
  { key: "Strategy", label: "Strategy" },
];

const COLUMNS = [
  { key: "name", label: "Index", align: "left" },
  { key: "close", label: "Last" },
  { key: "changePct", label: "Day" },
  { key: "change1mPct", label: "1M" },
  { key: "ema200", label: "200 EMA" },
  { key: "distFromEmaPct", label: "vs 200 EMA" },
  { key: "rsi14", label: "RSI (14)" },
  { key: "signal", label: "Signal", align: "left", sortable: false },
];

// The chart page resolves index names against Dhan's index master (every
// symbol in sector_indices.csv was checked to resolve to its own id, with
// no clash against a watchlist stock of the same name).
const chartHref = (symbol) => `/markets/chart?symbol=${encodeURIComponent(symbol)}`;

const GREEN = "#17A673";
const RED = "#E0473F";
const fmt = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (n) => (n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n)}%`);
const pctColor = (n) => (n == null ? "#8A90A0" : n >= 0 ? GREEN : RED);

function Check({ ok, label }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, color: ok ? GREEN : "#8A90A0", background: ok ? "#E6F7F1" : "#F0F1F4", padding: "3px 8px", borderRadius: 100, whiteSpace: "nowrap" }}>
      {ok ? "✓" : "✕"} {label}
    </span>
  );
}

function RsiCell({ value, max }) {
  if (value == null) return "—";
  const color = value < max ? GREEN : value > 70 ? RED : "#14171F";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
      <div style={{ width: 54, height: 5, background: "#F0F1F4", borderRadius: 100, position: "relative", overflow: "hidden" }} aria-hidden="true">
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.min(100, value)}%`, background: color, borderRadius: 100 }} />
        <div style={{ position: "absolute", left: `${max}%`, top: -2, bottom: -2, width: 1.5, background: "#14171F", opacity: 0.35 }} />
      </div>
      <span className="num" style={{ fontWeight: 700, color, minWidth: 34, textAlign: "right" }}>{fmt(value, 1)}</span>
    </div>
  );
}

function Stat({ label, value, sub, color }) {
  return (
    <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: "14px 18px", flex: "1 1 170px" }}>
      <span style={{ fontSize: 11, color: "#8A90A0", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</span>
      <div className="num" style={{ fontSize: 22, fontWeight: 800, marginTop: 4, color: color || "#14171F" }}>{value}</div>
      {sub && <span style={{ fontSize: 12, color: "#8A90A0" }}>{sub}</span>}
    </div>
  );
}

export default function SectorOverview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  // ?view= keeps the chosen tab on reload and in shared links.
  const view = searchParams.get("view") === "screen" ? "screen" : "day";
  const setView = (key) => setSearchParams(key === "day" ? {} : { view: key }, { replace: true });
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState({ key: null, dir: 1 });

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = () => {
      apiFetch("/api/markets/sectors")
        .then((res) => {
          if (!res.ok) throw new Error(res.status);
          return res.json();
        })
        .then((d) => {
          if (cancelled) return;
          setData(d);
          setError(false);
        })
        .catch(() => !cancelled && setError(true))
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

  const rule = data?.rule || { emaPeriod: 200, nearEmaPct: 1, rsiPeriod: 14, rsiMax: 35 };
  const all = data?.indices || [];
  const investable = all.filter((r) => r.investable);
  const vix = all.find((r) => r.category === "Volatility");

  const rows = useMemo(() => {
    let list = investable.filter((r) => (filter === "all" ? true : filter === "eligible" ? r.eligible : r.category === filter));
    if (sort.key) {
      list = [...list].sort((a, b) => {
        const av = a[sort.key];
        const bv = b[sort.key];
        if (av == null) return 1;
        if (bv == null) return -1;
        return (typeof av === "string" ? av.localeCompare(bv) : av - bv) * sort.dir;
      });
    } else {
      // Default: eligible first, then the CSV's own order.
      list = [...list].sort((a, b) => Number(b.eligible) - Number(a.eligible) || a.sortOrder - b.sortOrder);
    }
    return list;
  }, [investable, filter, sort]);

  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === "name" ? 1 : -1 }));

  const eligibleCount = investable.filter((r) => r.eligible).length;
  const belowEma = investable.filter((r) => r.distFromEmaPct != null && r.distFromEmaPct < 0).length;
  const oversold = investable.filter((r) => r.rsiCondition).length;

  return (
    <div style={{ width: "100%", padding: "clamp(24px, 5vw, 48px) clamp(16px, 5vw, 48px) 80px" }}>
      <style>{".sector-chart-icon{opacity:.35;transition:opacity .15s} .sector-chart-link:hover .sector-chart-icon,.sector-chart-link:focus-visible .sector-chart-icon{opacity:1} .sector-chart-link:hover > span:first-child{color:#4640DE}"}</style>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Markets</span>
          <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>Sector overview</h1>
          <p style={{ fontSize: 14.5, color: "#5B6270", marginTop: 6, maxWidth: 720, lineHeight: 1.6 }}>
            NSE sector, broad-market, thematic and strategy indices — today's market picture, and a daily investment-eligibility screen.
          </p>
        </div>

        <div role="tablist" aria-label="Sector overview views" style={{ display: "flex", gap: 4, borderBottom: "1px solid #E3E6EC" }}>
          {VIEWS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              style={{
                background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 14.5, fontWeight: 700, padding: "10px 16px", marginBottom: -1,
                color: view === key ? "#14171F" : "#8A90A0", borderBottom: `2px solid ${view === key ? "#4640DE" : "transparent"}`,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {view === "screen" && (
        <div style={{ background: "#14171F", borderRadius: 16, padding: "18px 22px", display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#F2A93B", letterSpacing: "0.06em", textTransform: "uppercase" }}>Investment-eligible rule</span>
            <span style={{ fontSize: 14.5, color: "white", lineHeight: 1.6 }}>
              Close <strong>below its {rule.emaPeriod}-day EMA</strong> or within <strong>{rule.nearEmaPct}%</strong> of it,{" "}
              <span style={{ color: "#F2A93B", fontWeight: 800 }}>and</span> daily <strong>RSI({rule.rsiPeriod}) under {rule.rsiMax}</strong>.
            </span>
          </div>
          {data?.updatedAt && (
            <span style={{ fontSize: 12, color: "#9297A8" }}>
              Updated {new Date(data.updatedAt).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST
            </span>
          )}
        </div>
        )}

        {error && !data ? (
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 40, textAlign: "center", fontSize: 14, color: "#5B6270" }}>
            Couldn't load sector data right now. It will retry automatically.
          </div>
        ) : !data ? (
          <div role="status" style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 40, textAlign: "center", fontSize: 14, color: "#5B6270" }}>
            Loading index data… the first load of the day can take up to half a minute.
          </div>
        ) : data.unavailable ? (
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 40, textAlign: "center", fontSize: 14, color: "#5B6270" }}>
            Sector data is temporarily unavailable. Please try again shortly.
          </div>
        ) : view === "day" ? (
          <SectorDayView data={data} />
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              <Stat label="Investment eligible" value={eligibleCount} sub={`of ${investable.length} indices`} color={eligibleCount ? GREEN : undefined} />
              <Stat label={`Below ${rule.emaPeriod} EMA`} value={belowEma} sub={`of ${investable.length}`} />
              <Stat label={`RSI under ${rule.rsiMax}`} value={oversold} sub={`of ${investable.length}`} />
              {vix && <Stat label="India VIX" value={fmt(vix.close)} sub={pct(vix.changePct) + " today"} color={pctColor(-vix.changePct)} />}
            </div>

            <div style={{ display: "flex", gap: 6, overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
              {FILTERS.map(({ key, label }) => {
                const count = key === "all" ? investable.length : key === "eligible" ? eligibleCount : investable.filter((r) => r.category === key).length;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setFilter(key)}
                    style={{
                      border: "1px solid #E3E6EC", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "8px 14px", borderRadius: 9, whiteSpace: "nowrap",
                      background: filter === key ? "#14171F" : "#FFFFFF", color: filter === key ? "#FFFFFF" : "#5B6270",
                    }}
                  >
                    {label} <span style={{ opacity: 0.6, fontWeight: 600 }}>{count}</span>
                  </button>
                );
              })}
            </div>

            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
              <div className="table-wrap">
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
                      {COLUMNS.map((c) => (
                        <th key={c.key} style={{ padding: "12px 14px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: c.align || "right", whiteSpace: "nowrap" }}>
                          {c.sortable === false ? (
                            c.label
                          ) : (
                            <button type="button" onClick={() => toggleSort(c.key)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit", color: sort.key === c.key ? "#14171F" : "inherit", textTransform: "inherit" }}>
                              {c.label}
                              {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                            </button>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {!rows.length ? (
                      <tr>
                        <td colSpan={COLUMNS.length} style={{ padding: "30px 16px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>
                          {filter === "eligible" ? "No index meets the rule right now." : "No indices in this group."}
                        </td>
                      </tr>
                    ) : (
                      rows.map((r) => (
                        <tr key={r.securityId} style={{ borderBottom: "1px solid #F0F1F4", background: r.eligible ? "#F3FBF8" : "transparent" }}>
                          <td style={{ padding: "12px 14px", whiteSpace: "nowrap" }}>
                            <Link to={chartHref(r.symbol)} className="sector-chart-link" title={`Open ${r.name} chart`} style={{ color: "inherit", textDecoration: "none", display: "inline-flex", flexDirection: "column" }}>
                              <span style={{ fontSize: 13.5, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 6 }}>
                                {r.name}
                                <svg className="sector-chart-icon" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#4640DE" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                  <path d="M2 12L6 7.5L9 10L14 4" />
                                  <path d="M10.5 4H14V7.5" />
                                </svg>
                              </span>
                              <span style={{ fontSize: 11.5, color: "#8A90A0" }}>
                                <span style={{ fontFamily: "'IBM Plex Mono', monospace", color: "#4640DE", fontWeight: 600 }}>{r.symbol}</span> · {r.category}
                              </span>
                            </Link>
                          </td>
                          <td className="num" style={{ padding: "12px 14px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>{fmt(r.close)}</td>
                          <td className="num" style={{ padding: "12px 14px", textAlign: "right", fontSize: 13, fontWeight: 600, color: pctColor(r.changePct) }}>{pct(r.changePct)}</td>
                          <td className="num" style={{ padding: "12px 14px", textAlign: "right", fontSize: 13, color: pctColor(r.change1mPct) }}>{pct(r.change1mPct)}</td>
                          <td className="num" style={{ padding: "12px 14px", textAlign: "right", fontSize: 13, color: "#5B6270", whiteSpace: "nowrap" }}>
                            {fmt(r.ema200)}
                            {r.approx && <span title={`Only ${r.bars} days of history available — the 200 EMA is still settling`} style={{ display: "block", fontSize: 10.5, color: "#B98A2E" }}>approx.</span>}
                          </td>
                          <td className="num" style={{ padding: "12px 14px", textAlign: "right", fontSize: 13, fontWeight: 700, color: r.priceCondition ? GREEN : "#14171F" }}>{pct(r.distFromEmaPct)}</td>
                          <td style={{ padding: "12px 14px", textAlign: "right", fontSize: 13 }}>
                            <RsiCell value={r.rsi14} max={rule.rsiMax} />
                          </td>
                          <td style={{ padding: "12px 14px" }}>
                            {r.eligible ? (
                              <span style={{ fontSize: 12, fontWeight: 800, color: "#FFFFFF", background: GREEN, padding: "5px 10px", borderRadius: 100, whiteSpace: "nowrap" }}>Eligible</span>
                            ) : (
                              <div style={{ display: "flex", gap: 5 }}>
                                <Check ok={r.priceCondition} label="EMA" />
                                <Check ok={r.rsiCondition} label="RSI" />
                              </div>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {data.failed?.length > 0 && (
              <p style={{ fontSize: 12.5, color: "#8A90A0", margin: 0 }}>Couldn't load: {data.failed.map((f) => f.name).join(", ")}.</p>
            )}
            <p style={{ fontSize: 12, color: "#8A90A0", margin: 0, lineHeight: 1.6 }}>
              Based on daily closes, with today's live price during market hours. A screen, not investment advice. "approx." marks indices with less than ~1.5 years of history available, where the 200-day EMA is less settled.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
