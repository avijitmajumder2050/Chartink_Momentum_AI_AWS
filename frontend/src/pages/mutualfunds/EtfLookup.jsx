import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { C, Kpi, Pct, card, inr, td, th, erText, aumText } from "./shared";

// Index -> ETF lookup. Index names are the same NSE names used in
// sector_indices.csv, so each one links to its chart and Sector Overview.

export default function EtfLookup({ data, selected, onSelect }) {
  const [q, setQ] = useState("");
  const withEtfs = useMemo(() => data.indices.filter((ix) => data.etfs[ix.name]), [data]);
  const list = withEtfs.filter((ix) => !q.trim() || ix.name.includes(q.trim().toUpperCase()) || ix.category.toUpperCase().includes(q.trim().toUpperCase()));
  const current = list.find((ix) => ix.name === selected) || list[0];

  const etfs = current ? [...(data.etfs[current.name] || [])].sort((a, b) => (b.aumCr ?? -1) - (a.aumCr ?? -1)) : [];
  const total = etfs.reduce((s, e) => s + (e.aumCr || 0), 0);
  const withEr = etfs.filter((e) => e.expenseRatio != null);
  const cheapest = [...withEr].sort((a, b) => a.expenseRatio - b.expenseRatio)[0];
  const linkedId = current ? data.linkedIndexFunds[current.name] : null;
  const linked = linkedId ? data.indexFunds.find((f) => f.id === linkedId) : null;

  return (
    <section style={{ ...card, overflow: "hidden" }} aria-label="Index to ETF lookup">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "18px 20px", borderBottom: `1px solid ${C.line}` }}>
        <div>
          <h2 id="etf-lookup" style={{ fontSize: 19, fontWeight: 800, margin: 0, scrollMarginTop: 90 }}>Index → ETF lookup</h2>
          <p style={{ margin: "3px 0 0", color: C.muted, fontSize: 13 }}>Pick an index to see the ETFs that track it, with symbol, AUM, expense ratio and latest price.</p>
        </div>
        <span style={{ fontSize: 12, color: C.faint }}>Prices, NAV, returns: NSE ETF feed · AUM, expense ratio: INDmoney</span>
      </div>
      <div className="mf-lk">
        <div className="mf-lk-list">
          <div style={{ padding: 14 }}>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter indices with ETFs…"
              aria-label="Filter indices"
              style={{ width: "100%", boxSizing: "border-box", height: 38, padding: "0 12px", border: `1px solid ${C.line}`, borderRadius: 9, fontFamily: "inherit", fontSize: 13 }}
            />
          </div>
          <div className="mf-lk-items">
            {!list.length && <p style={{ margin: "12px 8px", color: C.muted }}>No index with an ETF matches this filter.</p>}
            {list.map((ix) => {
              const n = data.etfs[ix.name].length;
              const on = current && ix.name === current.name;
              return (
                <button key={ix.name} type="button" aria-pressed={on} onClick={() => onSelect(ix.name)} className="mf-pick" style={{ background: on ? C.accent : "transparent", color: on ? "#fff" : C.ink }}>
                  <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>{ix.name}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: on ? "rgba(255,255,255,0.85)" : C.pos, whiteSpace: "nowrap" }}>{n} ETF{n > 1 ? "s" : ""}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          {!current ? (
            <div style={{ padding: 30, textAlign: "center", color: C.muted }}>No ETF for this selection.</div>
          ) : (
            <>
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: C.faint }}>Selected index</span>
                  <span className="num" style={{ fontSize: 22, fontWeight: 700 }}>{current.name}</span>
                  <span style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.accent, background: C.accentSoft, padding: "3px 9px", borderRadius: 100 }}>{current.category}</span>
                    <Link to={`/markets/chart?symbol=${encodeURIComponent(current.name)}`} style={{ fontSize: 12.5, fontWeight: 700, color: C.accent, textDecoration: "none" }}>Index chart ›</Link>
                    <Link to="/markets/sectors" style={{ fontSize: 12.5, fontWeight: 700, color: C.accent, textDecoration: "none" }}>Sector overview ›</Link>
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(110px,1fr))", gap: 10 }}>
                  <Kpi label="Tracking ETFs" value={etfs.length} />
                  <Kpi label="Combined AUM" value={total ? `₹${inr(total, 0)} Cr` : "—"} />
                  <Kpi label="Lowest cost" value={cheapest ? `${cheapest.expenseRatio.toFixed(2)}%` : "—"} />
                </div>
              </div>

              <div style={{ overflowX: "auto", border: `1px solid ${C.line}`, borderRadius: 12 }}>
                <table style={{ borderCollapse: "collapse", width: "100%" }}>
                  <thead>
                    <tr>
                      {["ETF symbol", "ETF", "AUM", "Expense", "Last price", "NAV", "1M", "1Y", ""].map((h, i) => (
                        <th key={i} style={{ ...th, textAlign: i >= 2 && i <= 7 ? "right" : "left" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {etfs.map((e) => (
                      <tr key={e.symbol}>
                        <td style={td}>
                          <Link to={`/markets/chart?symbol=${encodeURIComponent(e.symbol)}`} className="num" style={{ fontWeight: 800, color: C.ink, textDecoration: "none" }} title="Open chart">{e.symbol}</Link>
                        </td>
                        <td style={{ ...td, minWidth: 170 }}>
                          <div style={{ fontWeight: 600 }}>{e.name}</div>
                          <div style={{ fontSize: 12, color: C.faint }}>{e.amc}</div>
                        </td>
                        <td className="num" style={{ ...td, textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{e.aumCr != null ? `₹${inr(e.aumCr)} Cr` : <span style={{ color: C.faint }}>—</span>}</td>
                        <td className="num" style={{ ...td, textAlign: "right" }}>
                          {e.expenseRatio != null ? (
                            <span style={cheapest && e.symbol === cheapest.symbol && withEr.length > 1 ? { background: C.posSoft, borderRadius: 5, padding: "2px 6px" } : undefined}>{e.expenseRatio.toFixed(2)}%</span>
                          ) : (
                            <span style={{ color: C.faint }}>—</span>
                          )}
                        </td>
                        <td className="num" style={{ ...td, textAlign: "right" }}>₹{inr(e.lastPrice)}</td>
                        <td className="num" style={{ ...td, textAlign: "right", color: C.faint }}>₹{inr(e.nav)}</td>
                        <td style={{ ...td, textAlign: "right" }}><Pct v={e.change1m} /></td>
                        <td style={{ ...td, textAlign: "right" }}><Pct v={e.change1y} /></td>
                        <td style={{ ...td, textAlign: "right" }}>
                          <a href={e.url} target="_blank" rel="noopener noreferrer" aria-label={`View ${e.symbol}`} style={{ fontWeight: 800, color: C.accent, textDecoration: "none" }}>↗</a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {etfs.some((e) => e.aumCr == null) && <p style={{ margin: 0, fontSize: 12, color: C.faint }}>“—” in AUM or expense ratio: not retrieved for this ETF. Check the AMC factsheet.</p>}
              {linked && (
                <p style={{ margin: 0, fontSize: 13, color: C.ink2 }}>
                  Index fund on this page tracking this index: <strong>{linked.name}</strong> · AUM {aumText(linked.aumCr)} · expense ratio {erText(linked.expenseRatio)}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
