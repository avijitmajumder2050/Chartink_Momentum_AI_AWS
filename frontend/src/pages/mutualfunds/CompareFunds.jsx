import { C, LockIn, Pct, TrendBars, aumText, card, minText, selectStyle, td, th, erText } from "./shared";

// Side-by-side comparison of the funds ticked "Compare" anywhere on the
// page. Best value in each numeric column is highlighted (highest AUM and
// returns, lowest expense ratio) when at least two funds have that value.

export default function CompareFunds({ data, funds, compare, onToggle, onAdd, onClear }) {
  const rows = [...compare].map((id) => funds.find((f) => f.id === id)).filter(Boolean);
  const best = (key, dir) => {
    const v = rows.map((r) => r[key]).filter((x) => x != null);
    if (v.length < 2) return null;
    return dir > 0 ? Math.max(...v) : Math.min(...v);
  };
  const B = { aumCr: best("aumCr", 1), return1y: best("return1y", 1), cagr3y: best("cagr3y", 1), cagr5y: best("cagr5y", 1), expenseRatio: best("expenseRatio", -1) };
  const hl = (r, key, node) => (r[key] != null && B[key] === r[key] ? <span style={{ background: C.posSoft, borderRadius: 5, padding: "2px 6px" }}>{node}</span> : node);

  return (
    <section style={{ ...card, overflow: "hidden" }} aria-label="Compare funds">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "18px 20px", borderBottom: `1px solid ${C.line}` }}>
        <div>
          <h2 id="compare" style={{ fontSize: 19, fontWeight: 800, margin: 0, scrollMarginTop: 90 }}>Compare funds</h2>
          <p style={{ margin: "3px 0 0", color: C.muted, fontSize: 13 }}>Tick “Compare” on any fund, or add one here. The best value in each column is highlighted.</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <select
            value=""
            onChange={(e) => e.target.value && onAdd(e.target.value)}
            aria-label="Add a fund to compare"
            style={{ ...selectStyle, maxWidth: 280 }}
          >
            <option value="">+ Add fund…</option>
            <optgroup label="Index funds">
              {data.indexFunds.map((f) => (
                <option key={f.id} value={f.id} disabled={compare.has(f.id)}>{f.name}</option>
              ))}
            </optgroup>
            {data.equityCategories.map((c) => (
              <optgroup key={c} label={c}>
                {data.equityFunds.filter((f) => f.category === c).map((f) => (
                  <option key={f.id} value={f.id} disabled={compare.has(f.id)}>{f.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <button type="button" onClick={onClear} disabled={!rows.length} style={{ ...selectStyle, cursor: rows.length ? "pointer" : "default", opacity: rows.length ? 1 : 0.5 }}>Clear all</button>
        </div>
      </div>

      {!rows.length ? (
        <div style={{ margin: 16, padding: "36px 20px", textAlign: "center", color: C.muted, border: `1px dashed ${C.line}`, borderRadius: 12 }}>
          <b style={{ display: "block", color: C.ink, fontSize: 15, marginBottom: 4 }}>No funds selected</b>
          Tick “Compare” on a fund card, or pick one from “Add fund”.
        </div>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  {["", "Fund", "Category", "AUM", "1Y", "3Y CAGR", "5Y CAGR", "Expense", "Exit load", "Lock-in", "Min lumpsum / SIP", "Risk", "Trend", "Data as of"].map((h, i) => (
                    <th key={i} style={{ ...th, textAlign: [3, 4, 5, 6, 7, 10, 13].includes(i) ? "right" : "left" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td style={td}>
                      <input type="checkbox" checked onChange={() => onToggle(r.id)} aria-label={`Remove ${r.name} from comparison`} style={{ width: 17, height: 17, accentColor: C.accent }} />
                    </td>
                    <td style={{ ...td, minWidth: 240 }}>
                      <div style={{ fontWeight: 700 }}>{r.name}</div>
                      <div style={{ fontSize: 11.5, fontWeight: 700, color: r.kind === "Index Fund" ? C.accent : C.pos }}>{r.kind}</div>
                    </td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{r.category}</td>
                    <td className="num" style={{ ...td, textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{hl(r, "aumCr", aumText(r.aumCr))}</td>
                    <td style={{ ...td, textAlign: "right" }}>{hl(r, "return1y", <Pct v={r.return1y} />)}</td>
                    <td style={{ ...td, textAlign: "right" }}>{hl(r, "cagr3y", <Pct v={r.cagr3y} />)}</td>
                    <td style={{ ...td, textAlign: "right" }}>{hl(r, "cagr5y", <Pct v={r.cagr5y} />)}</td>
                    <td className="num" style={{ ...td, textAlign: "right" }}>{hl(r, "expenseRatio", erText(r.expenseRatio))}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{r.exitLoad}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}><LockIn f={r} /></td>
                    <td className="num" style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>{minText(r)}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{r.risk}</td>
                    <td style={td}><TrendBars f={r} /></td>
                    <td className="num" style={{ ...td, textAlign: "right", whiteSpace: "nowrap", color: C.faint }}>{r.dataDate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ margin: 0, padding: "10px 20px 14px", fontSize: 12, color: C.faint }}>Trend bars show 1Y, 3Y and 5Y returns on one scale (−10% to +25%).</p>
        </>
      )}
    </section>
  );
}
