import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

// Quarterly Results Scanner (Markets › Results Scanner). Presets are open
// to every signed-in user; building custom criteria needs Pro/Premium —
// the API enforces the same rule (app.py api_results_scanner), this only
// decides what the page lets you edit. Data: connectors/results_scanner.py.

const C = {
  ink: "#1C1917", dim: "#57534E", faint: "#78716C", line: "#E7E5E4", soft: "#F0EEE9",
  ground: "#FAF9F6", card: "#FFFFFF", accent: "#4F46E5", accentInk: "#3730A3", accentTint: "#EEF2FF",
  up: "#15803D", down: "#B91C1C",
};
const SANS = "'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif";
const MONO = "'IBM Plex Mono', monospace";
const DISPLAY = "'Manrope', sans-serif";

const REVIEW_FLAGS = ["small_base", "yoy_decline", "extreme_move"];
const FLAG_LABEL = { financial: "Financial", small_base: "Tiny base", yoy_decline: "YoY down", extreme_move: "Extreme move" };
const TABS = [
  ["all", "All matches"],
  ["clean", "Clean"],
  ["fin", "Financials"],
  ["review", "Needs review"],
];
const COLUMNS = [
  ["symbol", "Company", "text"],
  ["reported", "First seen", "text"],
  ["sales_qoq", "Sales QoQ", "pct"],
  ["ebitda_qoq", "EBITDA QoQ", "pct"],
  ["opm_qoq", "OPM QoQ", "pct"],
  ["profit_qoq", "Profit QoQ", "pct"],
  ["eps_qoq", "EPS QoQ", "pct"],
  ["profit_yoy", "Profit YoY", "pct"],
  ["sales_yoy", "Sales YoY", "pct"],
  ["flags", "Flags", "flags"],
];

let nextId = 1;
const withIds = (node) =>
  "rules" in node ? { ...node, id: nextId++, rules: node.rules.map(withIds) } : { ...node, id: nextId++ };
const stripIds = (node) =>
  "rules" in node
    ? { op: node.op, rules: node.rules.map(stripIds) }
    : { field: node.field, operator: node.operator, value: node.value };

function encodeState(state) {
  try {
    return btoa(unescape(encodeURIComponent(JSON.stringify(state))));
  } catch {
    return "";
  }
}
function decodeState(text) {
  try {
    return JSON.parse(decodeURIComponent(escape(atob(text))));
  } catch {
    return null;
  }
}

const fmtPct = (v) =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

function inTab(row, tab) {
  if (tab === "all") return true;
  if (tab === "clean") return row.flags.length === 0;
  if (tab === "fin") return row.flags.includes("financial");
  return row.flags.some((f) => REVIEW_FLAGS.includes(f));
}

const control = {
  font: `500 14px ${SANS}`, padding: "10px 12px", border: "1px solid #D6D3D1", borderRadius: 10,
  background: C.card, minHeight: 44, boxSizing: "border-box", color: C.ink, minWidth: 0,
};
const chip = (active) => ({
  border: `1px solid ${active ? C.accent : "#D6D3D1"}`, background: active ? C.accentTint : C.card,
  color: active ? C.accentInk : "#44403C", font: `${active ? 600 : 500} 13px ${SANS}`,
  padding: "10px 14px", borderRadius: 999, minHeight: 40, cursor: "pointer",
});
const ghostBtn = {
  border: "1px dashed #A8A29E", background: "transparent", color: "#44403C", font: `500 13px ${SANS}`,
  padding: "10px 14px", borderRadius: 10, minHeight: 40, cursor: "pointer",
};

function Segmented({ options, value, onChange, small, label }) {
  return (
    <div role="group" aria-label={label} style={{ display: "flex", background: C.soft, borderRadius: small ? 8 : 10, padding: small ? 3 : 4 }}>
      {options.map(([key, text, disabled, title]) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            disabled={disabled}
            title={title}
            onClick={() => onChange(key)}
            style={{
              border: 0, cursor: disabled ? "not-allowed" : "pointer",
              background: active ? (small ? C.accent : C.card) : "transparent",
              color: active ? (small ? "#FFF" : C.ink) : disabled ? "#A8A29E" : C.dim,
              font: small ? `600 12px ${MONO}` : `${active ? 600 : 500} 13px ${SANS}`,
              padding: small ? "6px 12px" : "10px 14px", borderRadius: small ? 6 : 8,
              boxShadow: active && !small ? "0 1px 2px rgba(0,0,0,.08)" : "none", minHeight: small ? 0 : 40,
            }}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

function RuleRow({ rule, fields, operators, locked, onChange, onRemove }) {
  const between = rule.operator === "between";
  const num = (s) => (s === "" || s === "-" ? s : Number(s));
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
      <select aria-label="Field" disabled={locked} value={rule.field} onChange={(e) => onChange({ ...rule, field: e.target.value })} style={{ ...control, flex: "2 1 180px" }}>
        {fields.map((f) => (
          <option key={f.key} value={f.key}>{f.label}{f.key === "opm_qoq" ? " (relative)" : ""}</option>
        ))}
      </select>
      <select
        aria-label="Operator"
        disabled={locked}
        value={rule.operator}
        onChange={(e) => {
          const op = e.target.value;
          const v = Array.isArray(rule.value) ? rule.value : [rule.value, rule.value];
          onChange({ ...rule, operator: op, value: op === "between" ? v : v[0] });
        }}
        style={{ ...control, font: `600 14px ${MONO}`, flex: "0 1 96px" }}
      >
        {operators.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
      {between ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center", flex: "1 1 160px" }}>
          {[0, 1].map((i) => (
            <input
              key={i}
              aria-label={i ? "High" : "Low"}
              disabled={locked}
              inputMode="decimal"
              value={rule.value[i]}
              onChange={(e) => {
                const v = [...rule.value];
                v[i] = num(e.target.value);
                onChange({ ...rule, value: v });
              }}
              style={{ ...control, font: `600 14px ${MONO}`, width: "100%" }}
            />
          ))}
        </div>
      ) : (
        <input
          aria-label="Value"
          disabled={locked}
          inputMode="decimal"
          value={rule.value}
          onChange={(e) => onChange({ ...rule, value: num(e.target.value) })}
          style={{ ...control, font: `600 14px ${MONO}`, flex: "1 1 110px" }}
        />
      )}
      <button type="button" aria-label="Remove condition" disabled={locked} onClick={onRemove}
        style={{ border: 0, background: "transparent", color: C.faint, width: 44, height: 44, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", cursor: locked ? "not-allowed" : "pointer" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" /></svg>
      </button>
    </div>
  );
}

function Group({ group, fields, operators, locked, onChange, onRemove, depth = 0 }) {
  const update = (i, node) => onChange({ ...group, rules: group.rules.map((r, j) => (j === i ? node : r)) });
  const remove = (i) => onChange({ ...group, rules: group.rules.filter((_, j) => j !== i) });
  const add = (node) => onChange({ ...group, rules: [...group.rules, withIds(node)] });
  const blank = { field: "sales_qoq", operator: ">", value: 0 };
  return (
    <div style={{ border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10, background: depth ? C.card : "#FCFBF9" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <Segmented
          small
          label="Group logic"
          value={group.op}
          options={[["AND", "AND", locked], ["OR", "OR", locked]]}
          onChange={(op) => onChange({ ...group, op })}
        />
        <span style={{ fontSize: 13, color: C.dim, flex: 1 }}>{group.op === "AND" ? "All conditions must match" : "Any condition can match"}</span>
        {onRemove && !locked && (
          <button type="button" onClick={onRemove} style={{ ...ghostBtn, border: 0 }}>Remove group</button>
        )}
      </div>
      {group.rules.map((r, i) =>
        "rules" in r ? (
          <Group key={r.id} group={r} fields={fields} operators={operators} locked={locked} depth={depth + 1} onChange={(n) => update(i, n)} onRemove={() => remove(i)} />
        ) : (
          <RuleRow key={r.id} rule={r} fields={fields} operators={operators} locked={locked} onChange={(n) => update(i, n)} onRemove={() => remove(i)} />
        ),
      )}
      {!locked && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, paddingTop: 4 }}>
          <button type="button" style={ghostBtn} onClick={() => add(blank)}>+ Add condition</button>
          {depth < 2 && (
            <button type="button" style={ghostBtn} onClick={() => add({ op: group.op === "AND" ? "OR" : "AND", rules: [blank] })}>+ Add group</button>
          )}
        </div>
      )}
    </div>
  );
}

function FlagBadges({ flags, tips }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {flags.map((f) => {
        const fin = f === "financial";
        return (
          <span key={f} title={tips[f] || ""} style={{ display: "inline-block", fontSize: 12, fontWeight: 600, fontFamily: SANS, color: fin ? "#1E40AF" : "#92400E", background: fin ? "#DBEAFE" : "#FEF3C7", padding: "4px 8px", borderRadius: 6 }}>
            {FLAG_LABEL[f] || f}
          </span>
        );
      })}
    </div>
  );
}

function hasInvalid(node) {
  if ("rules" in node) return node.rules.length === 0 || node.rules.some(hasInvalid);
  const vals = Array.isArray(node.value) ? node.value : [node.value];
  return vals.some((v) => typeof v !== "number" || Number.isNaN(v));
}

export default function ResultsScanner() {
  const { user } = useAuth();
  const isPro = user.role === "admin" || user.plan === "pro" || user.plan === "premium";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState("");
  const [quarter, setQuarter] = useState("");
  const [criteria, setCriteria] = useState(null);
  const [presetId, setPresetId] = useState("qoq_momentum");
  const [excludeFin, setExcludeFin] = useState(false);
  const [excludeNeg, setExcludeNeg] = useState(true);
  const [minCap, setMinCap] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("all");
  const [sort, setSort] = useState({ key: "profit_qoq", dir: -1 });
  const autoRan = useRef(false);

  useEffect(() => {
    apiFetch("/api/results-scanner/meta")
      .then((r) => r.json().then((d) => (r.ok ? d : Promise.reject(new Error(d.error || "Couldn't load the scanner")))))
      .then((d) => {
        setMeta(d);
        const shared = decodeState(searchParams.get("q") || "");
        if (shared?.criteria) {
          setCriteria(withIds(shared.criteria));
          setPresetId(shared.preset || "");
          setQuarter(shared.quarter || d.quarters[0]?.key || "");
          setExcludeFin(!!shared.exf);
          setExcludeNeg(shared.exn !== false);
          setMinCap(shared.cap ?? "");
        } else {
          setCriteria(withIds(d.presets[0].criteria));
          setQuarter(d.quarters[0]?.key || "");
        }
      })
      .catch((e) => setMetaError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once; the URL is only read on arrival
  }, []);

  function run(over = {}) {
    const crit = over.criteria || criteria;
    if (!crit || hasInvalid(crit)) {
      setError({ message: "Every condition needs a number, and every group at least one condition." });
      return;
    }
    const pid = over.presetId ?? presetId;
    const body = {
      source: "screener",
      quarter,
      criteria: stripIds(crit),
      exclude_financials: excludeFin,
      exclude_negative_base: excludeNeg,
      min_market_cap: minCap === "" ? null : Number(minCap),
    };
    setLoading(true);
    setError(null);
    setSearchParams({ q: encodeState({ criteria: body.criteria, preset: pid, quarter, exf: excludeFin, exn: excludeNeg, cap: minCap }) }, { replace: true });
    apiFetch("/api/results-scanner", { method: "POST", body: JSON.stringify(body) })
      .then((r) => r.json().then((d) => (r.ok ? d : Promise.reject(d))))
      .then((d) => {
        setResult(d);
        setTab("all");
      })
      .catch((d) => setError({ message: d?.error || "The scan failed. Try again.", code: d?.code }))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (meta && criteria && quarter && !autoRan.current) {
      autoRan.current = true;
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- first scan once the page has its defaults
  }, [meta, criteria, quarter]);

  function applyPreset(p) {
    const c = withIds(p.criteria);
    setPresetId(p.id);
    setCriteria(c);
    run({ criteria: c, presetId: p.id });
  }

  function editCriteria(next) {
    setCriteria(next);
    setPresetId("");
  }

  function relax(condition) {
    // Remove the single condition that knocked out the most companies.
    const drop = (node) =>
      "rules" in node
        ? { ...node, rules: node.rules.filter((r) => "rules" in r || JSON.stringify(stripIds(r)) !== JSON.stringify(condition)).map(drop) }
        : node;
    const next = drop(criteria);
    editCriteria(next);
    run({ criteria: next, presetId: "" });
  }

  const rows = useMemo(() => {
    if (!result) return [];
    const list = result.rows.filter((r) => inTab(r, tab));
    const { key, dir } = sort;
    return [...list].sort((a, b) => {
      const x = a[key], y = b[key];
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
    });
  }, [result, tab, sort]);

  const counts = useMemo(() => {
    const out = {};
    TABS.forEach(([k]) => (out[k] = result ? result.rows.filter((r) => inTab(r, k)).length : 0));
    return out;
  }, [result]);

  function exportCsv() {
    const head = ["Symbol", "Company", "First seen", ...COLUMNS.slice(2, 9).map((c) => c[1] + " %"), "Flags"];
    const lines = rows.map((r) => [r.symbol, r.name, r.reported || "", ...COLUMNS.slice(2, 9).map((c) => (r[c[0]] ?? "") === "" ? "" : Number(r[c[0]]).toFixed(2)), r.flags.join(" ")]);
    const csv = [head, ...lines].map((l) => l.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `results-scanner-${result?.quarter || "scan"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const fetchedText = result?.fetched_at || meta?.fetched_at
    ? new Date(result?.fetched_at || meta.fetched_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })
    : "not yet";
  const locked = !isPro;

  return (
    <div style={{ fontFamily: SANS, color: C.ink, background: C.ground, minHeight: "100vh", width: "100%" }}>
      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "32px 16px 64px", display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 13, color: C.dim }}>Markets / Results Scanner</div>
            <h1 style={{ margin: 0, fontFamily: DISPLAY, fontWeight: 800, fontSize: "clamp(26px, 4vw, 34px)", letterSpacing: "-0.02em" }}>Quarterly Results Scanner</h1>
            <p style={{ margin: 0, fontSize: 15, color: C.dim }}>Set QoQ and YoY criteria and find companies whose latest quarter clears every rule.</p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
            <Segmented
              label="Data source"
              value="screener"
              onChange={() => {}}
              options={[
                ["trendlyne", "Trendlyne", true, "Not available: Trendlyne's robots.txt disallows automated access to Rapid Results"],
                ["screener", "screener.in"],
              ]}
            />
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: C.dim }}>
              Quarter
              <select value={quarter} onChange={(e) => setQuarter(e.target.value)} style={control}>
                {(meta?.quarters || []).map((q) => (
                  <option key={q.key} value={q.key}>{q.label} · {q.reported} reported</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {metaError && <Notice tone="error">{metaError}</Notice>}

        <section aria-label="Criteria" style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 16, padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 16, marginRight: 6 }}>Presets</span>
            {(meta?.presets || []).map((p) => (
              <button key={p.id} type="button" style={chip(p.id === presetId)} onClick={() => applyPreset(p)}>{p.name}</button>
            ))}
          </div>

          {criteria && (
            <div style={{ position: "relative" }}>
              <Group group={criteria} fields={meta.fields} operators={meta.operators} locked={locked} onChange={editCriteria} />
              {locked && (
                <div style={{ marginTop: 10, fontSize: 13, color: C.dim, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  Presets are free. Building your own conditions needs Pro.
                  <Link to="/pricing" style={{ fontWeight: 600 }}>View plans</Link>
                </div>
              )}
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 20, fontSize: 14, color: "#44403C" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 44 }} title="A % change off a zero or negative previous value is left blank and fails the condition">
                <input type="checkbox" checked={excludeNeg} onChange={(e) => setExcludeNeg(e.target.checked)} style={{ width: 18, height: 18, accentColor: C.accent }} /> Exclude negative base
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 44 }}>
                <input type="checkbox" checked={excludeFin} onChange={(e) => setExcludeFin(e.target.checked)} style={{ width: 18, height: 18, accentColor: C.accent }} /> Exclude financials
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 44 }}>
                Min market cap (₹ Cr)
                <input inputMode="decimal" value={minCap} placeholder="Any" onChange={(e) => setMinCap(e.target.value.replace(/[^0-9.]/g, ""))} style={{ ...control, width: 90, font: `500 14px ${MONO}` }} />
              </label>
            </div>
            <button type="button" onClick={() => run()} disabled={loading || !criteria}
              style={{ border: 0, background: C.accent, color: "#FFF", font: `600 15px ${SANS}`, padding: "12px 24px", borderRadius: 10, minHeight: 48, display: "flex", alignItems: "center", gap: 8, cursor: loading ? "wait" : "pointer", opacity: loading ? 0.75 : 1 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.5" y2="16.5" /></svg>
              {loading ? "Scanning…" : "Run scan"}
            </button>
          </div>
        </section>

        <section aria-label="Results" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {error && (
            <Notice tone="error">
              {error.message}
              {error.code === "PRO_REQUIRED" && <> <Link to="/pricing" style={{ fontWeight: 600 }}>View plans</Link></>}
            </Notice>
          )}

          {result && (
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 28 }}>{result.matched}</span>
                <span style={{ fontSize: 15, color: "#44403C" }}>of {result.total_reported} companies reported for {result.quarter_label} match</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", fontSize: 13, color: C.dim }}>
                <span>Source: screener.in company pages · fetched {fetchedText}{result.cached ? " · cached" : ""}</span>
                <button type="button" onClick={exportCsv} disabled={!rows.length}
                  style={{ border: "1px solid #D6D3D1", background: C.card, color: "#44403C", font: `500 13px ${SANS}`, padding: "10px 14px", borderRadius: 10, minHeight: 40, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12" /><polyline points="7 10 12 15 17 10" /><path d="M5 21h14" /></svg>
                  Export CSV
                </button>
              </div>
            </div>
          )}

          {result && (
            <div role="tablist" aria-label="Result groups" style={{ display: "flex", flexWrap: "wrap", gap: 6, borderBottom: `1px solid ${C.line}` }}>
              {TABS.map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  style={{ border: 0, borderBottom: `2px solid ${tab === k ? C.accent : "transparent"}`, background: "transparent", color: tab === k ? C.accentInk : C.dim, font: `600 14px ${SANS}`, padding: "12px 14px", minHeight: 44, marginBottom: -1, cursor: "pointer" }}>
                  {label} <span style={{ fontFamily: MONO, fontSize: 12, marginLeft: 4 }}>{counts[k]}</span>
                </button>
              ))}
            </div>
          )}

          {result && tab === "fin" && (
            <Notice tone="info">EBITDA and OPM are not meaningful for banks, NBFCs and insurers. Judge these on NII, NIM, NPA and credit cost.</Notice>
          )}
          {result && tab === "review" && (
            <Notice tone="warn">These pass the rules, but the numbers are distorted by a tiny base, an extreme jump or falling YoY profit. Check the 4–5 quarter trend before trusting them.</Notice>
          )}

          {(loading || result) && (
            <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 960 }}>
                <thead>
                  <tr>
                    {COLUMNS.map(([key, label, type]) => {
                      const active = sort.key === key;
                      const sortable = type !== "flags";
                      return (
                        <th key={key} scope="col" aria-sort={active ? (sort.dir < 0 ? "descending" : "ascending") : "none"}
                          style={{ fontFamily: SANS, fontSize: 12, fontWeight: 600, color: active ? "#4338CA" : C.dim, textAlign: type === "pct" ? "right" : "left", padding: "10px 12px", borderBottom: `1px solid ${C.line}`, whiteSpace: "nowrap", background: "#F5F4F0" }}>
                          {sortable ? (
                            <button type="button" onClick={() => setSort({ key, dir: active ? -sort.dir : type === "pct" ? -1 : 1 })}
                              style={{ all: "unset", cursor: "pointer" }}>
                              {label}{active ? (sort.dir < 0 ? " ↓" : " ↑") : ""}
                            </button>
                          ) : label}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {loading
                    ? Array.from({ length: 8 }).map((_, i) => (
                        <tr key={i}>
                          {COLUMNS.map(([key]) => (
                            <td key={key} style={{ padding: "12px", borderBottom: "1px solid #F0EEE9" }}>
                              <div style={{ height: 12, borderRadius: 4, background: C.soft, width: key === "symbol" ? 120 : 56, marginLeft: key === "symbol" || key === "reported" || key === "flags" ? 0 : "auto" }} />
                            </td>
                          ))}
                        </tr>
                      ))
                    : rows.map((r) => (
                        <tr key={r.symbol} onClick={() => navigate(`/markets/research?symbol=${encodeURIComponent(r.symbol)}`)} style={{ cursor: "pointer" }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = "#F7F6FF")} onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
                          {COLUMNS.map(([key, , type]) => (
                            <td key={key} style={{ fontFamily: type === "pct" ? MONO : SANS, fontSize: type === "pct" ? 13 : 14, textAlign: type === "pct" ? "right" : "left", padding: "10px 12px", borderBottom: "1px solid #F0EEE9", whiteSpace: "nowrap",
                              color: type === "pct" ? (r[key] === null || r[key] === undefined ? "#A8A29E" : r[key] < 0 ? C.down : C.up) : key === "reported" ? C.dim : C.ink,
                              fontWeight: key === "symbol" || key === sort.key ? 600 : 400 }}>
                              {key === "symbol" ? (
                                <Link to={`/markets/research?symbol=${encodeURIComponent(r.symbol)}`} onClick={(e) => e.stopPropagation()} style={{ color: C.ink }} title={r.name}>
                                  {r.symbol}
                                </Link>
                              ) : type === "pct" ? fmtPct(r[key]) : type === "flags" ? <FlagBadges flags={r.flags} tips={meta?.flags || {}} /> : r[key] || "—"}
                            </td>
                          ))}
                        </tr>
                      ))}
                </tbody>
              </table>
              {!loading && result && !rows.length && (
                <div style={{ padding: "32px 16px", textAlign: "center", fontSize: 14, color: C.dim, display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>
                  {result.total_reported === 0 ? (
                    <span>No {result.quarter_label} results collected yet. The data is still being gathered; check back shortly.</span>
                  ) : result.matched === 0 && result.eliminated_most ? (
                    <>
                      <span>No company matches. <strong>{result.eliminated_most.rule}</strong> removed the most ({result.eliminated_most.count} of {result.total_reported}).</span>
                      {isPro ? (
                        <button type="button" style={chip(true)} onClick={() => relax(result.eliminated_most.condition)}>Relax: drop that condition</button>
                      ) : (
                        <span>Try another preset.</span>
                      )}
                    </>
                  ) : (
                    <span>Nothing in this tab.</span>
                  )}
                </div>
              )}
            </div>
          )}

          <p style={{ margin: 0, fontSize: 12, color: C.dim }}>
            Data from screener.in. OPM QoQ is a relative change; a % off a zero or negative base is blank unless “Exclude negative base” is off. Not investment advice.
          </p>
        </section>
      </main>
    </div>
  );
}

function Notice({ tone, children }) {
  const t = {
    error: { background: "#FEF2F2", border: "#FECACA", color: "#991B1B" },
    info: { background: "#EFF6FF", border: "#BFDBFE", color: "#1E3A8A" },
    warn: { background: "#FFFBEB", border: "#FDE68A", color: "#78350F" },
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : undefined} style={{ background: t.background, border: `1px solid ${t.border}`, color: t.color, borderRadius: 10, padding: "12px 14px", fontSize: 13 }}>
      {children}
    </div>
  );
}
