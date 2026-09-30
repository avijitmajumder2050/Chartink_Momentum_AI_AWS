import { useMemo, useState } from "react";
import { C, Kpi, LockIn, Pct, SORTS, TrendBars, aumText, card, inr, minText, selectStyle, sortFunds, td, th } from "./shared";

// Fund screener: filters are edited as a DRAFT and only take effect on
// "Apply" (the draft shows a live "N funds will match" count meanwhile),
// same interaction as the original MarketPulse page.

const DEFAULTS = { strategy: "all", bench: "all", cats: [], amc: "all", maxEr: 2.0, minAum: 0, risk: "all" };

function passes(f, F) {
  if (F.strategy === "passive" && f.kind !== "Index Fund") return false;
  if (F.strategy === "active" && f.kind === "Index Fund") return false;
  if (F.bench !== "all" && f.index !== F.bench) return false;
  if (F.cats.length && !F.cats.includes(f.category)) return false;
  if (F.amc !== "all" && f.amc !== F.amc) return false;
  if (f.expenseRatio > F.maxEr + 1e-9) return false;
  if (f.aumCr < F.minAum) return false;
  if (F.risk !== "all" && f.risk !== F.risk) return false;
  return true;
}

const activeCount = (F) =>
  (F.strategy !== "all") + (F.bench !== "all") + (F.cats.length > 0) + (F.amc !== "all") + (F.maxEr < DEFAULTS.maxEr) + (F.minAum > 0) + (F.risk !== "all");

const label = { display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: C.ink2 };
const val = { fontSize: 12, letterSpacing: 0, textTransform: "none", color: C.accent, fontWeight: 700 };

export default function Screener({ data, funds, compare, onToggle }) {
  const [draft, setDraft] = useState(DEFAULTS);
  const [applied, setApplied] = useState(DEFAULTS);
  const [sort, setSort] = useState("aumCr");

  const cats = useMemo(() => ["Index Fund", ...data.equityCategories], [data]);
  const amcs = useMemo(() => [...new Set(funds.map((f) => f.amc))].sort(), [funds]);
  const risks = useMemo(() => [...new Set(funds.map((f) => f.risk).filter(Boolean))], [funds]);
  const catCount = (c) => funds.filter((f) => f.category === c).length;

  const rows = useMemo(() => sortFunds(funds.filter((f) => passes(f, applied)), sort), [funds, applied, sort]);
  const draftMatches = useMemo(() => funds.filter((f) => passes(f, draft)).length, [funds, draft]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(applied);

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const apply = () => setApplied(draft);
  const resetAll = () => {
    setDraft(DEFAULTS);
    setApplied(DEFAULTS);
  };
  const clearOne = (k) => {
    setDraft((d) => ({ ...d, [k]: DEFAULTS[k] }));
    setApplied((a) => ({ ...a, [k]: DEFAULTS[k] }));
  };

  const tags = [];
  if (applied.strategy !== "all") tags.push(["strategy", applied.strategy === "passive" ? "Passive only" : "Active only"]);
  if (applied.bench !== "all") tags.push(["bench", `Benchmark: ${applied.bench}`]);
  if (applied.cats.length) tags.push(["cats", `Category: ${applied.cats.join(", ")}`]);
  if (applied.amc !== "all") tags.push(["amc", `AMC: ${applied.amc}`]);
  if (applied.maxEr < DEFAULTS.maxEr) tags.push(["maxEr", `Expense ≤ ${applied.maxEr.toFixed(2)}%`]);
  if (applied.minAum > 0) tags.push(["minAum", `AUM ≥ ₹${applied.minAum.toLocaleString("en-IN")} Cr`]);
  if (applied.risk !== "all") tags.push(["risk", `Risk: ${applied.risk}`]);

  const total = rows.reduce((t, f) => t + f.aumCr, 0);
  const cheapest = [...rows].sort((a, b) => a.expenseRatio - b.expenseRatio)[0];
  const best3 = rows.filter((f) => f.cagr3y != null).sort((a, b) => b.cagr3y - a.cagr3y)[0];

  return (
    <section style={{ ...card, overflow: "hidden" }} aria-label="Fund screener">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "18px 20px", borderBottom: `1px solid ${C.line}` }}>
        <div>
          <h2 id="screener" style={{ fontSize: 19, fontWeight: 800, margin: 0, scrollMarginTop: 90 }}>Fund screener</h2>
          <p style={{ margin: "3px 0 0", color: C.muted, fontSize: 13 }}>Set filters on the left and apply them. Matching index funds and equity mutual funds appear on the right.</p>
        </div>
        <span style={{ fontSize: 12, color: C.faint }}>{funds.length} funds · Direct Growth plans</span>
      </div>

      <div className="mf-scr">
        <aside className="mf-filters" aria-label="Screener filters">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: 12, borderBottom: `1px solid ${C.line}` }}>
            <span style={{ fontSize: 12.5, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase" }}>Filters</span>
            <button type="button" onClick={resetAll} style={{ border: 0, background: "transparent", color: C.muted, fontFamily: "inherit", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>↺ Reset</button>
          </div>

          {dirty && (
            <div role="status" style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "8px 10px", borderRadius: 9, background: C.warnSoft, color: C.warn, fontSize: 12 }}>
              <span>Unapplied edits · <b className="num">{draftMatches}</b> funds will match</span>
            </div>
          )}
          <button type="button" onClick={apply} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, width: "100%", height: 42, border: 0, borderRadius: 10, background: C.accent, color: "#fff", fontFamily: "inherit", fontWeight: 800, fontSize: 14, cursor: "pointer" }}>
            Apply filters
            <span className="num" style={{ background: "rgba(255,255,255,0.22)", borderRadius: 10, padding: "1px 8px", fontSize: 11.5 }}>{activeCount(draft)}</span>
          </button>

          <div className="mf-fg">
            <span style={label}>Investment strategy</span>
            <div role="group" aria-label="Investment strategy" style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 4, padding: 4, background: "#FFFFFF", border: `1px solid ${C.line}`, borderRadius: 9 }}>
              {[["all", "All"], ["passive", "Passive"], ["active", "Active"]].map(([k, l]) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={draft.strategy === k}
                  onClick={() => set({ strategy: k })}
                  style={{ height: 30, border: `1px solid ${draft.strategy === k ? C.accent : "transparent"}`, borderRadius: 7, background: draft.strategy === k ? C.accentSoft : "transparent", color: draft.strategy === k ? C.accent : C.muted, fontFamily: "inherit", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          <label className="mf-fg">
            <span style={label}>
              Benchmark index <span style={{ ...val, fontSize: 10.5 }}>Index funds</span>
            </span>
            <select value={draft.bench} onChange={(e) => set({ bench: e.target.value })} style={{ ...selectStyle, width: "100%" }}>
              <option value="all">All benchmark indices</option>
              {data.indexFunds.map((f) => (
                <option key={f.id} value={f.index}>{f.index}</option>
              ))}
            </select>
          </label>

          <div className="mf-fg">
            <span style={label}>Fund category</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {cats.map((c) => (
                <label key={c} className="mf-catrow">
                  <span>
                    <input
                      type="checkbox"
                      checked={draft.cats.includes(c)}
                      onChange={(e) => set({ cats: e.target.checked ? [...draft.cats, c] : draft.cats.filter((x) => x !== c) })}
                      style={{ width: 15, height: 15, accentColor: C.accent, verticalAlign: -2, margin: "0 6px 0 0" }}
                    />
                    {c === "Index Fund" ? "Index Fund (Passive)" : c}
                  </span>
                  <span className="num" style={{ fontSize: 11, color: C.faint }}>{catCount(c)}</span>
                </label>
              ))}
            </div>
          </div>

          <label className="mf-fg">
            <span style={label}>Fund house (AMC)</span>
            <select value={draft.amc} onChange={(e) => set({ amc: e.target.value })} style={{ ...selectStyle, width: "100%" }}>
              <option value="all">All fund houses</option>
              {amcs.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </label>

          <label className="mf-fg">
            <span style={label}>
              Max expense ratio <span className="num" style={val}>{draft.maxEr >= DEFAULTS.maxEr ? "Any" : `≤ ${draft.maxEr.toFixed(2)}%`}</span>
            </span>
            <input type="range" min="0.30" max="2.00" step="0.05" value={draft.maxEr} onChange={(e) => set({ maxEr: parseFloat(e.target.value) })} style={{ width: "100%", accentColor: C.accent }} />
            <span className="num" style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint }}><span>0.30%</span><span>1.15%</span><span>2.00%</span></span>
          </label>

          <label className="mf-fg">
            <span style={label}>
              Minimum fund AUM <span className="num" style={val}>{draft.minAum === 0 ? "₹0 Cr" : `≥ ₹${draft.minAum.toLocaleString("en-IN")} Cr`}</span>
            </span>
            <input type="range" min="0" max="50000" step="500" value={draft.minAum} onChange={(e) => set({ minAum: parseInt(e.target.value, 10) })} style={{ width: "100%", accentColor: C.accent }} />
            <span className="num" style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint }}><span>₹0</span><span>₹25k Cr</span><span>₹50k Cr</span></span>
          </label>

          <label className="mf-fg">
            <span style={label}>SEBI riskometer</span>
            <select value={draft.risk} onChange={(e) => set({ risk: e.target.value })} style={{ ...selectStyle, width: "100%" }}>
              <option value="all">All risk profiles</option>
              {risks.map((r) => (
                <option key={r} value={r}>{r} risk</option>
              ))}
            </select>
          </label>

          <p style={{ margin: 0, fontSize: 11.5, color: C.faint, lineHeight: 1.45 }}>Tracking error and star ratings aren't offered as filters — the sources used don't publish them.</p>
        </aside>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "18px 20px", minWidth: 0 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12.5, color: C.muted, marginRight: 6 }}>
              Showing <b className="num" style={{ color: C.ink }}>{rows.length}</b> of {funds.length} funds
            </span>
            {tags.map(([k, l]) => (
              <button key={k} type="button" onClick={() => clearOne(k)} aria-label={`Remove filter ${l}`} className="mf-tag">
                {l} <span aria-hidden="true">×</span>
              </button>
            ))}
            {tags.length > 0 && (
              <button type="button" onClick={resetAll} className="mf-tag" style={{ borderStyle: "dashed" }}>Reset all</button>
            )}
          </div>

          <div className="mf-kpis4">
            <Kpi label="Matching funds" value={rows.length} />
            <Kpi label="Combined AUM" value={rows.length ? `₹${inr(total, 0)} Cr` : "—"} />
            <Kpi label="Lowest cost" value={cheapest ? `${cheapest.expenseRatio.toFixed(2)}%` : "—"} sub={cheapest?.name} />
            <Kpi label="Best 3Y CAGR" value={best3 ? <Pct v={best3.cagr3y} /> : "—"} sub={best3?.name} />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: C.muted }}>
              Sort by
              <select value={sort} onChange={(e) => setSort(e.target.value)} style={selectStyle}>
                {SORTS.map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </select>
            </label>
          </div>

          {!rows.length ? (
            <div style={{ padding: "40px 20px", textAlign: "center", color: C.muted, border: `1px dashed ${C.line}`, borderRadius: 12 }}>
              <b style={{ display: "block", color: C.ink, fontSize: 15, marginBottom: 4 }}>No fund matches these filters</b>
              Raise the expense ratio limit, lower the minimum AUM, or reset the filters.
            </div>
          ) : (
            <div style={{ overflow: "auto", maxHeight: 620, border: `1px solid ${C.line}`, borderRadius: 12 }}>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ ...th, position: "sticky", top: 0, zIndex: 1, width: 40 }}><span className="sr-only-mf">Compare</span></th>
                    {["Fund", "Category", "AUM", "1Y", "3Y CAGR", "5Y CAGR", "Expense", "Exit load", "Lock-in", "Min lumpsum / SIP", "Trend", ""].map((h, i) => (
                      <th key={i} style={{ ...th, position: "sticky", top: 0, zIndex: 1, textAlign: [2, 3, 4, 5, 6, 9].includes(i) ? "right" : "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((f) => (
                    <tr key={f.id}>
                      <td style={td}>
                        <input type="checkbox" checked={compare.has(f.id)} onChange={() => onToggle(f.id)} aria-label={`Compare ${f.name}`} style={{ width: 17, height: 17, accentColor: C.accent }} />
                      </td>
                      <td style={{ ...td, minWidth: 230 }}>
                        <div style={{ fontWeight: 700 }}>{f.name}</div>
                        <div style={{ fontSize: 11.5, fontWeight: 700, color: f.kind === "Index Fund" ? C.accent : C.pos }}>
                          {f.kind}
                          {f.kind === "Index Fund" ? ` · ${f.index}` : ""}
                        </div>
                      </td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>{f.category}</td>
                      <td className="num" style={{ ...td, textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{aumText(f.aumCr)}</td>
                      <td style={{ ...td, textAlign: "right" }}><Pct v={f.return1y} /></td>
                      <td style={{ ...td, textAlign: "right" }}><Pct v={f.cagr3y} /></td>
                      <td style={{ ...td, textAlign: "right" }}><Pct v={f.cagr5y} /></td>
                      <td className="num" style={{ ...td, textAlign: "right" }}>{f.expenseRatio.toFixed(2)}%</td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>{f.exitLoad}</td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}><LockIn f={f} /></td>
                      <td className="num" style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>{minText(f)}</td>
                      <td style={td}><TrendBars f={f} w={72} h={24} /></td>
                      <td style={{ ...td, textAlign: "right" }}>
                        <a href={f.url} target="_blank" rel="noopener noreferrer" aria-label={`View ${f.name}`} style={{ fontWeight: 800, color: C.accent, textDecoration: "none" }}>↗</a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
