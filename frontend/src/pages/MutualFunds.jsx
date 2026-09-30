import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client";
import Screener from "./mutualfunds/Screener";
import CompareFunds from "./mutualfunds/CompareFunds";
import EtfLookup from "./mutualfunds/EtfLookup";
import { EquityFundCard, IndexFundCard } from "./mutualfunds/FundCards";
import { C, SORTS, SectionHead, card, inr, selectStyle, sortFunds } from "./mutualfunds/shared";

// Markets -> Mutual Funds. Integrated from the "MarketPulse Fund
// Watchlist" artifact: same sections, Quantile styling. Data is a
// hand-collected snapshot served from S3 (GET /api/markets/mutual-funds,
// uploads/mutual_funds.json — see upload_mutual_funds.py), not live.

const COMPARE_KEY = "quantile.mf.compare";
const DEFAULT_COMPARE = ["tata-m150m50", "nip-500m50", "hdfc-sc250i", "hdfc-mc"];

function loadCompare() {
  try {
    const saved = JSON.parse(localStorage.getItem(COMPARE_KEY) || "null");
    if (Array.isArray(saved)) return new Set(saved);
  } catch {
    // storage blocked or corrupt — fall back to the default selection
  }
  return new Set(DEFAULT_COMPARE);
}

function Insights({ data, funds }) {
  // Computed from the data (not hard-coded), so they stay true when the
  // snapshot in S3 is refreshed.
  const withEr = [...funds].sort((a, b) => a.expenseRatio - b.expenseRatio);
  const best5 = funds.filter((f) => f.cagr5y != null).sort((a, b) => b.cagr5y - a.cagr5y)[0];
  const largest = [...funds].sort((a, b) => b.aumCr - a.aumCr)[0];
  const niftyEtfs = (data.etfs.NIFTY || []).filter((e) => e.expenseRatio != null).sort((a, b) => a.expenseRatio - b.expenseRatio || (b.aumCr || 0) - (a.aumCr || 0));
  const items = [
    withEr[0] && { title: "Lowest cost", body: withEr[0].name, stat: `Expense ratio ${withEr[0].expenseRatio.toFixed(2)}% · ${withEr[0].category}`, icon: "M12 3v18M17 7H9.5a3 3 0 0 0 0 6h5a3 3 0 0 1 0 6H6" },
    best5 && { title: "Best 5-year CAGR", body: best5.name, stat: `${best5.cagr5y.toFixed(2)}% a year over 5 years · ${best5.category}`, icon: "M4 17l5-5 4 4 7-8M15 8h5v5" },
    largest && { title: "Largest fund", body: largest.name, stat: `AUM ₹${inr(largest.aumCr, 0)} Cr · ${largest.category}`, icon: "M5 20V14M10 20V10M15 20V6M20 20V3" },
    niftyEtfs[0] && { title: "Cheapest Nifty 50 ETF", body: `${niftyEtfs[0].symbol} · ${niftyEtfs[0].name}`, stat: `Expense ratio ${niftyEtfs[0].expenseRatio.toFixed(2)}% · ${data.etfs.NIFTY.length} Nifty 50 ETFs listed`, icon: "M3 12h4l3-7 4 14 3-7h4" },
  ].filter(Boolean);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))", gap: 16 }}>
      {items.map((it) => (
        <div key={it.title} style={{ ...card, display: "flex", gap: 14, padding: 18, minWidth: 0 }}>
          <span style={{ flexShrink: 0, width: 38, height: 38, borderRadius: 10, display: "grid", placeItems: "center", background: C.accentSoft, color: C.accent }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d={it.icon} />
            </svg>
          </span>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ fontSize: 13, fontWeight: 700, color: C.faint, margin: "0 0 3px", textTransform: "uppercase", letterSpacing: "0.04em" }}>{it.title}</h3>
            <p style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>{it.body}</p>
            <div className="num" style={{ marginTop: 6, fontSize: 12, color: C.muted }}>{it.stat}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function FundSearch({ data, funds, onPickFund, onPickIndex }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (s.length < 2) return [];
    const out = [];
    funds.forEach((f) => f.name.toLowerCase().includes(s) && out.push({ key: `f-${f.id}`, label: f.name, tag: f.category, go: () => onPickFund(f) }));
    Object.entries(data.etfs).forEach(([ix, list]) =>
      list.forEach((e) => (e.symbol.toLowerCase().includes(s) || e.name.toLowerCase().includes(s)) && out.push({ key: `e-${e.symbol}`, label: `${e.symbol} · ${e.name}`, tag: "ETF", go: () => onPickIndex(ix) })),
    );
    data.indices.forEach((ix) => data.etfs[ix.name] && ix.name.toLowerCase().includes(s) && out.push({ key: `i-${ix.name}`, label: ix.name, tag: "Index", go: () => onPickIndex(ix.name) }));
    return out.slice(0, 12);
  }, [q, data, funds, onPickFund, onPickIndex]);

  const pick = (h) => {
    h.go();
    setQ("");
    setOpen(false);
  };

  return (
    <div style={{ position: "relative", width: "min(360px, 100%)" }} onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <input
        type="search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "Enter" && hits[0]) pick(hits[0]);
        }}
        placeholder="Search fund, ETF or index…"
        aria-label="Search fund, ETF or index"
        style={{ width: "100%", boxSizing: "border-box", height: 42, padding: "0 14px", border: `1px solid ${C.line}`, borderRadius: 10, fontFamily: "inherit", fontSize: 14, background: "#FFFFFF" }}
      />
      {open && q.trim().length >= 2 && (
        <div style={{ position: "absolute", top: 48, left: 0, right: 0, zIndex: 30, background: "#FFFFFF", border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: "0 8px 28px rgba(20,23,31,0.14)", padding: 6, maxHeight: 360, overflow: "auto" }}>
          {!hits.length ? (
            <div style={{ padding: 10, color: C.muted, fontSize: 13 }}>No fund, ETF or index matches “{q}”.</div>
          ) : (
            hits.map((h) => (
              <button key={h.key} type="button" onClick={() => pick(h)} className="mf-hit">
                <span>{h.label}</span>
                <small style={{ color: C.faint, whiteSpace: "nowrap" }}>{h.tag}</small>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function MutualFunds() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [compare, setCompare] = useState(loadCompare);
  const [mcat, setMcat] = useState(null);
  const [msort, setMsort] = useState("cagr5y");
  const [lookupIndex, setLookupIndex] = useState("NIFTY");

  useEffect(() => {
    apiFetch("/api/markets/mutual-funds")
      .then((res) => {
        if (!res.ok) throw new Error(res.status);
        return res.json();
      })
      .then(setData)
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(COMPARE_KEY, JSON.stringify([...compare]));
    } catch {
      // not remembered — fine
    }
  }, [compare]);

  const funds = useMemo(() => (data && !data.unavailable ? [...data.indexFunds, ...data.equityFunds] : []), [data]);
  const category = mcat || data?.equityCategories?.[0];
  const toggle = (id) =>
    setCompare((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  if (error || data?.unavailable) {
    return (
      <div style={{ padding: "80px 20px", textAlign: "center", color: C.muted }}>Mutual fund data is unavailable right now. Please try again shortly.</div>
    );
  }
  if (!data) {
    return (
      <div role="status" style={{ padding: "80px 20px", textAlign: "center", color: C.muted }}>Loading mutual funds…</div>
    );
  }

  // Ranked by 5Y CAGR within the category (the rank badge), then sorted by the chosen key.
  const ranked = sortFunds(data.equityFunds.filter((f) => f.category === category), "cagr5y").map((f, i) => ({ f, rank: i + 1 }));
  const shown = msort === "cagr5y" ? ranked : sortFunds(ranked.map((r) => r.f), msort).map((f) => ranked.find((r) => r.f.id === f.id));

  return (
    <div style={{ width: "100%", padding: "clamp(24px, 5vw, 44px) clamp(16px, 5vw, 48px) 80px" }}>
      <style>{`
        .mf-scr { display: grid; grid-template-columns: clamp(220px, 26%, 290px) minmax(0, 1fr); align-items: start }
        .mf-filters { display: flex; flex-direction: column; gap: 16px; padding: 18px; background: ${C.surface2}; border-right: 1px solid ${C.line}; align-self: stretch; min-width: 0 }
        .mf-fg { display: flex; flex-direction: column; gap: 7px }
        .mf-catrow { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 6px; border-radius: 6px; cursor: pointer; font-size: 13px; color: ${C.ink2} }
        .mf-catrow:hover { background: ${C.accentSoft} }
        .mf-tag { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 10px; border-radius: 13px; border: 1px solid ${C.line}; background: #fff; color: ${C.ink2}; font: inherit; font-size: 12px; cursor: pointer }
        .mf-tag:hover { border-color: ${C.neg}; color: ${C.neg} }
        .mf-kpis4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px }
        .mf-grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap: 18px }
        .mf-grid5 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 236px), 1fr)); gap: 14px }
        .mf-lk { display: grid; grid-template-columns: 300px minmax(0, 1fr); min-height: 480px }
        .mf-lk-list { border-right: 1px solid ${C.line}; background: ${C.surface2}; display: flex; flex-direction: column; min-width: 0 }
        .mf-lk-items { flex: 1; overflow-y: auto; max-height: 540px; padding: 0 8px 10px; display: flex; flex-direction: column; gap: 2px }
        .mf-pick { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 36px; padding: 0 12px; border: 0; border-radius: 8px; cursor: pointer; text-align: left; font: inherit }
        .mf-pick[aria-pressed="false"]:hover { background: ${C.accentSoft} !important }
        .mf-hit { display: flex; justify-content: space-between; gap: 12px; width: 100%; text-align: left; border: 0; background: transparent; padding: 8px 10px; border-radius: 7px; cursor: pointer; font: inherit; font-size: 13px; color: ${C.ink} }
        .mf-hit:hover, .mf-hit:focus-visible { background: ${C.accentSoft} }
        .mf-tabs { display: flex; gap: 4px; padding: 4px; background: #fff; border: 1px solid ${C.line}; border-radius: 10px; overflow-x: auto; max-width: 100% }
        .sr-only-mf { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap }
        @media (max-width: 1100px) { .mf-kpis4 { grid-template-columns: repeat(2, minmax(0, 1fr)) } }
        @media (max-width: 900px) { .mf-lk { grid-template-columns: 1fr } .mf-lk-list { border-right: 0; border-bottom: 1px solid ${C.line} } .mf-lk-items { max-height: 220px } }
        @media (max-width: 680px) { .mf-scr { grid-template-columns: 1fr } .mf-filters { border-right: 0; border-bottom: 1px solid ${C.line} } }
      `}</style>

      <div style={{ maxWidth: 1280, margin: "0 auto", display: "flex", flexDirection: "column", gap: 28 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <span style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Markets</span>
            <h1 style={{ fontSize: 32, fontWeight: 800, margin: "8px 0 0" }}>Mutual funds &amp; ETFs</h1>
            <p style={{ margin: "6px 0 0", color: C.muted, fontSize: 15 }}>Index funds, top equity funds by category and ETFs — AUM, returns, cost and trend.</p>
            <span
              style={{
                display: "inline-flex", alignItems: "center", gap: 8, marginTop: 12, minHeight: 28, padding: "4px 12px", borderRadius: 14, fontSize: 12, fontWeight: 700,
                background: data.refreshedOn ? C.posSoft : C.warnSoft, color: data.refreshedOn ? C.pos : C.warn,
              }}
            >
              {data.refreshedOn ? "Updated daily" : "Snapshot, not live"} · {data.asOf}
            </span>
          </div>
          <FundSearch
            data={data}
            funds={funds}
            onPickFund={(f) => {
              if (f.kind === "Equity MF") {
                setMcat(f.category);
                scrollTo("equity-funds");
              } else scrollTo("index-funds");
            }}
            onPickIndex={(ix) => {
              setLookupIndex(ix);
              scrollTo("etf-lookup");
            }}
          />
        </div>

        <Screener data={data} funds={funds} compare={compare} onToggle={toggle} />

        <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <SectionHead id="index-funds" title="Index funds" sub="Passive funds tracking broad-market and factor indices." meta="Direct Growth plans" />
          <div className="mf-grid3">
            {data.indexFunds.map((f) => (
              <IndexFundCard key={f.id} f={f} compare={compare} onToggle={toggle} />
            ))}
          </div>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <SectionHead id="equity-funds" title="Equity mutual funds" sub="Top 5 funds in each SEBI equity category, ranked by 5-year CAGR. Direct Growth plans." />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", justifyContent: "space-between" }}>
            <div role="tablist" aria-label="Equity category" className="mf-tabs">
              {data.equityCategories.map((c) => (
                <button
                  key={c}
                  type="button"
                  role="tab"
                  aria-selected={category === c}
                  onClick={() => setMcat(c)}
                  style={{ height: 34, padding: "0 14px", border: 0, borderRadius: 7, background: category === c ? C.ink : "transparent", color: category === c ? "#fff" : C.muted, fontFamily: "inherit", fontWeight: 700, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" }}
                >
                  {c}
                </button>
              ))}
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: C.muted }}>
              Sort by
              <select value={msort} onChange={(e) => setMsort(e.target.value)} style={selectStyle}>
                <option value="cagr5y">5Y CAGR (rank)</option>
                {SORTS.filter((s) => s.key !== "cagr5y").map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="mf-grid5">
            {shown.map(({ f, rank }) => (
              <EquityFundCard key={f.id} f={f} rank={rank} compare={compare} onToggle={toggle} />
            ))}
          </div>
        </section>

        <EtfLookup data={data} selected={lookupIndex} onSelect={setLookupIndex} />

        <CompareFunds
          data={data}
          funds={funds}
          compare={compare}
          onToggle={toggle}
          onAdd={(id) => setCompare((s) => new Set([...s, id]))}
          onClear={() => setCompare(new Set())}
        />

        <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <SectionHead id="insights" title="Quick insights" sub="From the funds and ETFs on this page." />
          <Insights data={data} funds={funds} />
        </section>

        <footer style={{ display: "flex", flexDirection: "column", gap: 10, padding: "16px 20px", background: C.surface2, border: `1px solid ${C.line}`, borderRadius: 12, fontSize: 12.5, color: C.ink2 }}>
          <p style={{ margin: 0 }}>
            <strong style={{ color: C.ink }}>Disclaimer:</strong> Mutual fund and ETF investments are subject to market risks. Past performance does not guarantee future returns. This page is a data summary, not investment advice.
          </p>
          <p style={{ margin: 0 }}>
            {data.refreshedOn
              ? "NAV, 1Y/3Y/5Y returns and ETF prices are refreshed every trading day from AMFI and NSE data; returns are calculated from NAV history (3Y and 5Y annualised). AUM, expense ratio, exit load and minimums are updated periodically (dates shown with each fund)."
              : `Figures were collected on ${new Date(`${data.collectedOn}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} from public pages and are not live.`}{" "}
            Direct Growth plans. “—” means the figure isn't available or the fund is too new.
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
            {[...(data.refreshSources || []), ...data.sources].map((s) => (
              <li key={s.label}>
                {s.label}:{" "}
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ color: C.accent }}>{s.name}</a>
                ) : (
                  s.name
                )}
              </li>
            ))}
          </ul>
        </footer>
      </div>
    </div>
  );
}
