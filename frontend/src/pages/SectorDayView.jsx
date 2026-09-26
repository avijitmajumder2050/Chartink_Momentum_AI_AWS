import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

// Sector Overview's "Day view" tab — a dark market-overview dashboard
// (layout per sector_overview.png): index cards with 30-session
// sparklines, market breadth, a sector heat-map grid, a 5-day sector trend
// chart, top movers and data-derived insights. Everything comes from the
// same GET /api/markets/sectors payload as the Investment screen tab.

const T = {
  bg: "#0F131C",
  card: "#161B27",
  border: "#262C3A",
  text: "#F4F5F8",
  text2: "#A6ACBB",
  muted: "#6F7687",
  up: "#4ADE9C",
  down: "#F87171",
  grid: "#232938",
};

// Heat-map fills: diverging, green arm / red arm, neutral gray midpoint,
// three steps each by |% change|. Market convention (green up, red down);
// the value itself stays in primary text with a sign + arrow, so the
// fill is never the only carrier of direction.
const HEAT = {
  up: ["#1B3A2F", "#1D5139", "#1F6B45"],
  down: ["#3E2228", "#58262E", "#772A34"],
  flat: "#252A36",
};
function heatFill(pct) {
  if (pct == null || Math.abs(pct) < 0.1) return HEAT.flat;
  const arm = pct > 0 ? HEAT.up : HEAT.down;
  const a = Math.abs(pct);
  return arm[a < 0.5 ? 0 : a < 1 ? 1 : 2];
}

// Sector tiles: every "Sector" index plus two sector-like thematics.
const EXTRA_TILES = new Set(["NIFTY ENERGY", "NIFTYINFRA"]);

// Trend chart shows the TREND_COUNT sectors with the strongest (or, with
// the toggle, weakest) 5-session momentum, re-picked on every refresh.
// Because the set changes, colour is by rank slot (1st = blue, ...)
// rather than tied to a sector; the legend names every line with its
// 5-day %, so identity never rests on colour alone. Colours are the
// reference palette's dark categorical slots 1-5, validated on T.card.
const TREND_COUNT = 5;
const TREND_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];
// Look-back options for the trend chart, in trading sessions (a week =
// 5). The API sends 30 recent closes per index, enough for all three.
const TREND_PERIODS = [
  { key: "1w", label: "1 week", sessions: 5 },
  { key: "2w", label: "2 weeks", sessions: 10 },
  { key: "3w", label: "3 weeks", sessions: 15 },
];

const fmt = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
// Sign taken from the value as displayed, so -0.03 at 1dp shows "0.0",
// not "−0.0".
const signed = (n, d = 2) => {
  if (n == null) return "—";
  const r = Number(n.toFixed(d));
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${fmt(Math.abs(r), d)}`;
};
const chartHref = (symbol) => `/markets/chart?symbol=${encodeURIComponent(symbol)}`;
const shortName = (name) => name.replace(/^Nifty\s+/i, "");
// Tile labels: a few official names are too long for a tile.
const TILE_NAMES = { "Financial Services": "Fin. Services", "Consumer Durables": "Cons. Durables", Infrastructure: "Infra" };
const tileName = (name) => TILE_NAMES[shortName(name)] || shortName(name);
const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

const card = { background: T.card, border: `1px solid ${T.border}`, borderRadius: 14 };

// ---- icons (16px strokes, currentColor) ----
const ICON_PATHS = {
  bank: "M2 6.5L8 3l6 3.5M3 7v5.5M6 7v5.5M10 7v5.5M13 7v5.5M2 13.5h12",
  finance: "M8 2.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 0 0 0-11zM6 10l4-4M6.2 6.2h.01M9.8 9.8h.01",
  it: "M2.5 3.5h11v7h-11zM6 13.5h4M8 10.5v3",
  auto: "M3 10.5V8l1.5-3.5h7L13 8v2.5M3 10.5h10M4.5 12.5v-2M11.5 12.5v-2M5 8h6",
  fmcg: "M2 3h2l1.5 7h7L14 5H4.8M6.5 13a.5.5 0 1 0 0-.01M11.5 13a.5.5 0 1 0 0-.01",
  pharma: "M5.5 10.5l5-5a2.1 2.1 0 0 1 3 3l-5 5a2.1 2.1 0 0 1-3-3zM8 8l2.5 2.5",
  health: "M8 13.5S2.5 10.3 2.5 6.3A2.8 2.8 0 0 1 8 5a2.8 2.8 0 0 1 5.5 1.3c0 4-5.5 7.2-5.5 7.2zM5 8h1.5l1-1.5 1.5 3 1-1.5H11",
  metal: "M8 2.5l5 2.8v5.4l-5 2.8-5-2.8V5.3zM3 5.3l5 2.8 5-2.8M8 8.1v5.4",
  realty: "M2.5 7.5L8 3l5.5 4.5M4 6.5v7h8v-7M6.5 13.5v-3.5h3v3.5",
  media: "M8 8.5v5M5.5 13.5h5M5.2 5.7a4 4 0 0 1 5.6 0M3.4 3.9a6.5 6.5 0 0 1 9.2 0M8 8.5a.5.5 0 1 0 0-.01",
  durables: "M2.5 3.5h11v7.5h-11zM5.5 13.5h5",
  oil: "M8 2.5S4 7 4 9.8a4 4 0 0 0 8 0C12 7 8 2.5 8 2.5z",
  energy: "M9 2L4 9h4l-1 5 5-7H8z",
  infra: "M3 13.5V6l5-3.5L13 6v7.5M6 13.5V9h4v4.5M2 13.5h12",
};
const SYMBOL_ICON = {
  BANKNIFTY: "bank", "NIFTY PVT BANK": "bank", "NIFTY PSU BANK": "bank", FINNIFTY: "finance",
  NIFTYIT: "it", "NIFTY AUTO": "auto", "NIFTY FMCG": "fmcg", "NIFTY PHARMA": "pharma",
  "NIFTY HEALTHCARE": "health", "NIFTY METAL": "metal", "NIFTY REALTY": "realty", "NIFTY MEDIA": "media",
  "NIFTY CONSR DURBL": "durables", "NIFTY OIL AND GAS": "oil", "NIFTY ENERGY": "energy", NIFTYINFRA: "infra",
};
function Icon({ name, size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICON_PATHS[name] || ICON_PATHS.metal} />
    </svg>
  );
}

// ---- sparkline ----
function Sparkline({ points, width = 150, height = 52 }) {
  if (!points || points.length < 2) return null;
  const values = points.map((p) => p.c);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const up = values[values.length - 1] >= values[0];
  const color = up ? T.up : T.down;
  const xy = values.map((v, i) => [(i / (values.length - 1)) * width, 4 + (1 - (v - min) / span) * (height - 8)]);
  const line = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const gid = `spark-${up ? "u" : "d"}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true" style={{ flexShrink: 1, minWidth: 0, maxWidth: "100%" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${line} ${width},${height}`} fill={`url(#${gid})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function IndexCard({ row }) {
  if (!row) return null;
  const up = (row.change ?? 0) >= 0;
  return (
    <Link to={chartHref(row.symbol)} className="dv-hover" style={{ ...card, padding: "18px 22px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, textDecoration: "none", flex: "1 1 260px", minWidth: 0 }}>
      <div style={{ minWidth: 0 }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, color: T.text2, letterSpacing: "0.02em" }}>{row.name.toUpperCase()}</span>
        <div className="num" style={{ fontSize: 26, fontWeight: 800, color: T.text, marginTop: 4 }}>{fmt(row.close)}</div>
        <span className="num" style={{ fontSize: 13.5, fontWeight: 700, color: up ? T.up : T.down }}>
          {up ? "▲" : "▼"} {signed(row.change)} ({signed(row.changePct)}%)
        </span>
      </div>
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, minWidth: 0, maxWidth: "45%" }}>
        <Sparkline points={row.recent} />
        <span style={{ fontSize: 10.5, color: T.muted }}>30D</span>
      </span>
    </Link>
  );
}

function BreadthCard({ breadth }) {
  const total = breadth ? breadth.advancing + breadth.declining : 0;
  const advPct = total ? (breadth.advancing / total) * 100 : null;
  return (
    <div style={{ ...card, padding: "18px 22px", flex: "1 1 280px", minWidth: 0 }}>
      <span style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Market breadth</span>
      {advPct == null ? (
        <p style={{ fontSize: 13, color: T.muted, margin: "14px 0 0" }}>Calculating from the tracked watchlist — check back in a minute.</p>
      ) : (
        <>
          <div style={{ fontSize: 12.5, color: T.text2, marginTop: 8 }}>Advancing / Declining</div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 4 }}>
            <span className="num" style={{ fontSize: 20, fontWeight: 800, whiteSpace: "nowrap" }}>
              <span style={{ color: T.up }}>{breadth.advancing}</span>
              <span style={{ color: T.muted }}> / </span>
              <span style={{ color: T.down }}>{breadth.declining}</span>
            </span>
            <div
              role="img"
              aria-label={`${fmt(advPct, 0)}% of tracked stocks advancing`}
              style={{ flex: 1, height: 8, borderRadius: 100, overflow: "hidden", display: "flex", gap: 2, background: T.bg }}
            >
              <div style={{ width: `${advPct}%`, background: T.up, borderRadius: 100 }} />
              <div style={{ flex: 1, background: T.down, borderRadius: 100 }} />
            </div>
            <span className="num" style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{fmt(advPct, 0)}%</span>
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>{breadth.sampleSize} stocks tracked · {breadth.unchanged} unchanged</div>
        </>
      )}
    </div>
  );
}

function SectorTile({ row, mode }) {
  const value = mode === "pct" ? row.changePct : row.change;
  const up = (value ?? 0) > 0;
  const down = (value ?? 0) < 0;
  return (
    <Link
      to={chartHref(row.symbol)}
      className="dv-tile"
      title={`${row.name}: ${signed(row.changePct)}% (${signed(row.change)} pts) — open chart`}
      style={{ background: heatFill(row.changePct), borderRadius: 12, padding: "14px 14px 12px", display: "flex", gap: 12, alignItems: "flex-start", textDecoration: "none", color: T.text, border: "1px solid rgba(255,255,255,0.06)", minWidth: 0 }}
    >
      <span className="dv-tile-icon" style={{ width: 34, height: 34, borderRadius: "50%", background: "rgba(255,255,255,0.08)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, color: T.text }}>
        <Icon name={SYMBOL_ICON[row.symbol]} />
      </span>
      <span style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.25 }}>{tileName(row.name)}</span>
        <span className="num" style={{ fontSize: 19, fontWeight: 800, marginTop: 2 }}>
          <span style={{ fontSize: 12, marginRight: 4, color: up ? T.up : down ? T.down : T.muted }}>{up ? "▲" : down ? "▼" : "•"}</span>
          {mode === "pct" ? `${signed(value)}%` : signed(value)}
        </span>
        <span style={{ fontSize: 11, color: T.text2, marginTop: 2, fontFamily: "'IBM Plex Mono', monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={row.symbol}>{row.symbol}</span>
      </span>
      <svg className="dv-tile-chev" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke={T.text2} strokeWidth="1.6" aria-hidden="true" style={{ marginTop: 4, flexShrink: 0 }}>
        <path d="M4.5 2.5L8 6L4.5 9.5" />
      </svg>
    </Link>
  );
}

// ---- 5-day trend chart (indexed to 100) ----
function TrendChart({ series }) {
  const [hover, setHover] = useState(null);
  // Drawn at its real pixel width (not a fixed viewBox scaled to fit),
  // so axis text stays 11px instead of shrinking with the card.
  const wrapRef = useRef(null);
  const [W, setW] = useState(400);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(240, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = 220;
  const pad = { l: 38, r: 12, t: 12, b: 28 };
  const dates = series[0]?.points.map((p) => p.t) || [];
  const all = series.flatMap((s) => s.points.map((p) => p.v));
  if (!dates.length || !all.length) return <div ref={wrapRef} />;
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  const step = hi - lo > 6 ? 2 : hi - lo > 3 ? 1 : 0.5;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  if (hi === lo) hi = lo + step;
  const ticks = [];
  for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(v);
  const x = (i) => pad.l + (i / (dates.length - 1)) * (W - pad.l - pad.r);
  // A date label is ~48px wide at 11px; below ~64px apart, label every
  // other session (always keeping the latest).
  const labelEvery = Math.max(1, Math.ceil(64 / ((W - pad.l - pad.r) / (dates.length - 1))));
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);

  function onMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (dates.length - 1));
    setHover(Math.max(0, Math.min(dates.length - 1, i)));
  }

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`Sector performance over the last ${dates.length - 1} sessions, indexed to 100`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} style={{ display: "block", cursor: "crosshair", maxWidth: "100%" }}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={v === 100 ? "#3A4152" : T.grid} strokeWidth="1" strokeDasharray={v === 100 ? "" : "3 4"} />
            <text x={pad.l - 8} y={y(v) + 4} fontSize="11" fill={T.muted} textAnchor="end" className="num">{fmt(v, step < 1 ? 1 : 0)}</text>
          </g>
        ))}
        {dates.map((d, i) => ((dates.length - 1 - i) % labelEvery === 0 ? (
          <text key={d} x={x(i)} y={H - 8} fontSize="11" fill={T.muted} textAnchor={i === dates.length - 1 ? "end" : "middle"}>{shortDate(d)}</text>
        ) : null))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke={T.text2} strokeWidth="1" opacity="0.5" />}
        {series.map((s) => (
          <polyline key={s.symbol} points={s.points.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {hover != null &&
          series.map((s) => (
            <circle key={s.symbol} cx={x(hover)} cy={y(s.points[hover].v)} r="4" fill={s.color} stroke={T.card} strokeWidth="2" />
          ))}
      </svg>
      {hover != null && (
        <div
          style={{
            position: "absolute", top: 8, left: `${(x(hover) / W) * 100}%`, transform: hover > dates.length / 2 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
            background: "#0B0E15", border: `1px solid ${T.border}`, borderRadius: 8, padding: "8px 10px", fontSize: 12, color: T.text, pointerEvents: "none", whiteSpace: "nowrap", zIndex: 2,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{shortDate(dates[hover])}</div>
          {[...series].sort((a, b) => b.points[hover].v - a.points[hover].v).map((s) => (
            <div key={s.symbol} style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "space-between" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color }} />
                {s.label}
              </span>
              <span className="num" style={{ color: T.text2 }}>{signed(s.points[hover].v - 100)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MoversCard({ title, rows, up }) {
  return (
    <div style={{ ...card, padding: "16px 18px", flex: "1 1 220px", minWidth: 0 }}>
      <span style={{ fontSize: 14.5, fontWeight: 700, color: up ? T.up : T.down, display: "flex", alignItems: "center", gap: 6 }}>
        {up ? "↗" : "↘"} {title}
      </span>
      {!rows?.length ? (
        <p style={{ fontSize: 12.5, color: T.muted, margin: "12px 0 0" }}>Calculating — check back in a minute.</p>
      ) : (
        rows.map((m, i) => (
          <Link key={m.symbol} to={chartHref(m.symbol)} className="dv-row" style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "9px 0", borderTop: i ? `1px solid ${T.grid}` : "none", marginTop: i ? 0 : 8, textDecoration: "none" }}>
            <span style={{ fontSize: 13, color: T.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              <span style={{ color: T.muted, marginRight: 8 }}>{i + 1}.</span>
              {m.symbol}
            </span>
            <span className="num" style={{ fontSize: 13, fontWeight: 700, color: up ? T.up : T.down }}>{signed(m.changePct)}%</span>
          </Link>
        ))
      )}
    </div>
  );
}

function pctChange(points, n) {
  if (!points || points.length < n + 1) return null;
  const a = points[points.length - 1 - n].c;
  const b = points[points.length - 1].c;
  return a ? ((b - a) / a) * 100 : null;
}

function buildInsights(tiles, breadth) {
  const withChange = tiles.filter((t) => t.changePct != null);
  if (!withChange.length) return [];
  const byDay = [...withChange].sort((a, b) => b.changePct - a.changePct);
  const best = byDay[0];
  const worst = byDay[byDay.length - 1];
  const upCount = withChange.filter((t) => t.changePct > 0).length;
  const fiveDay = withChange.map((t) => ({ t, v: pctChange(t.recent, 5) })).filter((x) => x.v != null).sort((a, b) => b.v - a.v);
  const insights = [
    best.changePct >= 0
      ? { tone: "up", title: `${shortName(best.name)} leads today`, body: `Up ${fmt(best.changePct)}% — best of ${withChange.length} sectors` }
      : { tone: "down", title: `${shortName(best.name)} held up best`, body: `Down only ${fmt(Math.abs(best.changePct))}% on a weak day` },
    worst.changePct < 0
      ? { tone: "down", title: `${shortName(worst.name)} under most pressure`, body: `Down ${fmt(Math.abs(worst.changePct))}% — weakest sector today` }
      : { tone: "up", title: `Every sector is up`, body: `Even the weakest, ${shortName(worst.name)}, gained ${fmt(worst.changePct)}%` },
  ];
  if (fiveDay.length) {
    const top = fiveDay[0];
    insights.push({ tone: top.v >= 0 ? "info" : "down", title: `${shortName(top.t.name)} strongest over 5 days`, body: `${signed(top.v)}% across the last 5 sessions` });
  }
  if (breadth?.sampleSize) {
    const positive = breadth.advancing >= breadth.declining;
    insights.push({ tone: positive ? "up" : "down", title: `Market breadth is ${positive ? "positive" : "negative"}`, body: `${breadth.advancing} advanced vs ${breadth.declining} declined · ${upCount} of ${withChange.length} sectors up` });
  } else {
    insights.push({ tone: upCount >= withChange.length / 2 ? "up" : "down", title: `${upCount} of ${withChange.length} sectors up today`, body: "Across the sector indices above" });
  }
  return insights;
}

const INSIGHT_TONE = {
  up: { bg: "rgba(74,222,156,0.14)", color: T.up, glyph: "↑" },
  down: { bg: "rgba(248,113,113,0.14)", color: T.down, glyph: "↓" },
  info: { bg: "rgba(57,135,229,0.18)", color: "#6DA7EC", glyph: "→" },
};

export default function SectorDayView({ data }) {
  const [mode, setMode] = useState("pct");
  const rows = useMemo(() => data?.indices || [], [data]);
  const bySymbol = useMemo(() => Object.fromEntries(rows.map((r) => [r.symbol, r])), [rows]);

  const tiles = useMemo(
    () => rows.filter((r) => r.category === "Sector" || EXTRA_TILES.has(r.symbol)).sort((a, b) => (b.changePct ?? -99) - (a.changePct ?? -99)),
    [rows],
  );

  const [trendPeriodKey, setTrendPeriodKey] = useState("1w");
  const trendPeriod = TREND_PERIODS.find((p) => p.key === trendPeriodKey) || TREND_PERIODS[0];

  // Every tile sector indexed to 100 over the chosen period (common
  // dates taken from NIFTY so all lines share one x-axis).
  const trendPool = useMemo(() => {
    const need = trendPeriod.sessions + 1; // N changes need N+1 closes
    const dates = bySymbol.NIFTY?.recent?.slice(-need).map((p) => p.t);
    if (!dates || dates.length < need) return [];
    return tiles
      .map((row) => {
        const byDate = Object.fromEntries((row.recent || []).map((p) => [p.t, p.c]));
        const vals = dates.map((d) => byDate[d]);
        if (vals.some((v) => v == null)) return null;
        return {
          symbol: row.symbol,
          label: tileName(row.name),
          points: dates.map((t, i) => ({ t, v: (vals[i] / vals[0]) * 100 })),
          periodChange: (vals[vals.length - 1] / vals[0] - 1) * 100,
        };
      })
      .filter(Boolean);
  }, [bySymbol, tiles, trendPeriod]);

  const [trendMode, setTrendMode] = useState("positive");
  const trend = useMemo(() => {
    const ranked = [...trendPool].sort((a, b) => (trendMode === "positive" ? b.periodChange - a.periodChange : a.periodChange - b.periodChange));
    return ranked.slice(0, TREND_COUNT).map((s, i) => ({ ...s, color: TREND_COLORS[i] }));
  }, [trendPool, trendMode]);

  const insights = useMemo(() => buildInsights(tiles, data?.breadth), [tiles, data]);
  const nifty = bySymbol.NIFTY;
  const asOf = nifty?.asOf;

  return (
    <div style={{ background: T.bg, borderRadius: 20, padding: "clamp(16px, 3vw, 28px)", color: T.text, display: "flex", flexDirection: "column", gap: 18 }}>
      <style>{`
        .dv-hover { transition: border-color .15s }
        .dv-hover:hover { border-color: #3A4152 !important }
        .dv-tile { transition: transform .12s, filter .12s }
        .dv-tile:hover, .dv-tile:focus-visible { filter: brightness(1.18); transform: translateY(-1px) }
        .dv-row:hover span:first-child { color: #FFFFFF; text-decoration: underline }
        .dv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(150px, 100%), 1fr)); gap: 10px }
        @media (max-width: 520px) { .dv-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px } .dv-tile { padding: 11px 10px 10px !important } .dv-tile-icon, .dv-tile-chev { display: none !important } }
        .dv-main { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: 18px; align-items: start }
        @media (max-width: 960px) { .dv-main { grid-template-columns: minmax(0, 1fr) } }
      `}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 10 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: T.text, margin: 0 }}>Sector view</h2>
          <p style={{ fontSize: 13.5, color: T.text2, margin: "4px 0 0" }}>All sectors with today's performance, trend and key movers</p>
        </div>
        {asOf && (
          <div style={{ textAlign: "right", fontSize: 12.5, color: T.text2 }}>
            <div>{new Date(`${asOf}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</div>
            {data?.updatedAt && <div style={{ color: T.muted }}>Updated {new Date(data.updatedAt).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST</div>}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
        <IndexCard row={nifty} />
        <IndexCard row={bySymbol["NIFTY 500"]} />
        <BreadthCard breadth={data?.breadth} />
      </div>

      <div className="dv-main">
        <div style={{ ...card, padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <span style={{ fontSize: 16, fontWeight: 700 }}>Sector performance</span>
            <div role="group" aria-label="Show change as" style={{ display: "flex", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 9, padding: 3 }}>
              {[["pct", "% Change"], ["pts", "Points"]].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={mode === key}
                  onClick={() => setMode(key)}
                  style={{ border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "6px 12px", borderRadius: 7, background: mode === key ? "#2A78D6" : "transparent", color: mode === key ? "#FFFFFF" : T.text2 }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="dv-grid">
            {tiles.map((r) => (
              <SectorTile key={r.securityId} row={r} mode={mode} />
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
          <div style={{ ...card, padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 16, fontWeight: 700 }}>
                Sector trend <span style={{ fontSize: 13, fontWeight: 500, color: T.text2 }}>(last {trendPeriod.sessions} sessions, indexed to 100)</span>
                <span style={{ display: "block", fontSize: 12, fontWeight: 500, color: T.muted, marginTop: 2 }}>
                  Top {TREND_COUNT} by {trendMode} momentum over {trendPeriod.label}
                </span>
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
                <span className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Trend period</span>
                <select
                  value={trendPeriodKey}
                  onChange={(e) => setTrendPeriodKey(e.target.value)}
                  style={{
                    appearance: "none", WebkitAppearance: "none", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, color: T.text, cursor: "pointer",
                    background: T.bg, border: `1px solid ${T.border}`, borderRadius: 9, padding: "8px 30px 8px 12px", colorScheme: "dark",
                  }}
                >
                  {TREND_PERIODS.map((p) => (
                    <option key={p.key} value={p.key}>{p.label}</option>
                  ))}
                </select>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke={T.text2} strokeWidth="1.6" aria-hidden="true" style={{ position: "absolute", right: 11, pointerEvents: "none" }}>
                  <path d="M2 3.5L5 6.5L8 3.5" />
                </svg>
              </label>
              <div role="group" aria-label="Momentum direction" style={{ display: "flex", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 9, padding: 3 }}>
                {[["positive", "▲ Positive"], ["negative", "▼ Negative"]].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={trendMode === key}
                    onClick={() => setTrendMode(key)}
                    style={{
                      border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "6px 11px", borderRadius: 7, whiteSpace: "nowrap",
                      background: trendMode === key ? (key === "positive" ? "#1F6B45" : "#772A34") : "transparent",
                      color: trendMode === key ? "#FFFFFF" : T.text2,
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              </div>
            </div>
            {trend.length ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 12, alignItems: "center" }}>
                <div style={{ flex: "1 1 260px", minWidth: 0 }}>
                  <TrendChart series={trend} />
                </div>
                <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10, flex: "0 0 auto" }}>
                  {trend.map((s) => (
                    <li key={s.symbol} style={{ display: "flex", alignItems: "center", fontSize: 13, justifyContent: "space-between", gap: 14, minWidth: 150 }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: T.text }}>
                        <span style={{ width: 10, height: 10, borderRadius: 3, background: s.color }} />
                        {s.label}
                      </span>
                      <span className="num" style={{ fontWeight: 700, color: T.text2 }}>{signed(s.periodChange, 1)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p style={{ fontSize: 13, color: T.muted }}>Not enough recent data.</p>
            )}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
            <MoversCard title="Top gainers" rows={data?.gainers} up />
            <MoversCard title="Top losers" rows={data?.losers} up={false} />
          </div>
        </div>
      </div>

      {insights.length > 0 && (
        <div style={{ ...card, padding: "16px 20px" }}>
          <span style={{ fontSize: 15, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "#F2A93B" }}>✦</span> Key insights
          </span>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginTop: 12 }}>
            {insights.map((ins) => {
              const tone = INSIGHT_TONE[ins.tone];
              return (
                <div key={ins.title} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <span style={{ width: 30, height: 30, borderRadius: "50%", background: tone.bg, color: tone.color, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, flexShrink: 0 }} aria-hidden="true">{tone.glyph}</span>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: T.text }}>{ins.title}</div>
                    <div style={{ fontSize: 12, color: T.text2, marginTop: 2 }}>{ins.body}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <p style={{ fontSize: 11.5, color: T.muted, margin: 0 }}>Click any index, sector or stock to open its chart. Breadth and movers come from the tracked watchlist.</p>
    </div>
  );
}
