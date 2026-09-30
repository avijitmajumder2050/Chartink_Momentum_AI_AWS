// Shared formatting, colours and small pieces for the Mutual Funds page.

export const C = {
  ink: "#14171F",
  ink2: "#33374A",
  muted: "#5B6270",
  faint: "#8A90A0",
  line: "#E3E6EC",
  line2: "#F0F1F4",
  surface2: "#F7F8FA",
  accent: "#4640DE",
  accentSoft: "#EEEDFD",
  pos: "#17A673",
  posSoft: "#E6F7F1",
  neg: "#E0473F",
  negSoft: "#FCEBEA",
  warn: "#8A6516",
  warnSoft: "#FBF2E1",
};

export const card = { background: "#FFFFFF", border: `1px solid ${C.line}`, borderRadius: 16 };

export const inr = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const aumText = (n) => (n == null ? "—" : `₹${inr(n, Number.isInteger(n) ? 0 : 2)} Cr`);
export const rupees = (n) => (n == null ? "—" : `₹${Number(n).toLocaleString("en-IN")}`);
export const erText = (v) => (v == null ? "—" : `${v.toFixed(2)}%`);
export const minText = (f) => (f.minLumpsum == null ? "—" : `${rupees(f.minLumpsum)} / ${rupees(f.minSip)}`);

export function Pct({ v }) {
  if (v == null) return <span style={{ color: C.faint }}>—</span>;
  const color = v > 0 ? C.pos : v < 0 ? C.neg : C.faint;
  return (
    <span className="num" style={{ color }}>
      {v > 0 ? "+" : ""}
      {v.toFixed(2)}%
    </span>
  );
}

export function LockIn({ f }) {
  if (!f.lockIn || f.lockIn === "None") return <span style={{ color: C.faint }}>None</span>;
  return <span style={{ fontSize: 12, fontWeight: 700, color: C.warn, background: C.warnSoft, padding: "2px 8px", borderRadius: 100 }}>{f.lockIn}</span>;
}

// 1Y / 3Y / 5Y returns as three small bars on one fixed scale (−10%..+25%),
// so bars are comparable across funds. Missing values show as a flat stub.
export function TrendBars({ f, w = 84, h = 26 }) {
  const vals = [f.return1y, f.cagr3y, f.cagr5y];
  const lo = -10;
  const hi = 25;
  const y = (v) => h - 4 - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (h - 8);
  const z = y(0);
  const bw = Math.max(10, Math.floor(w / 5));
  const gap = (w - 3 * bw) / 4;
  const label = `Returns 1Y ${f.return1y ?? "n/a"}%, 3Y ${f.cagr3y ?? "n/a"}%, 5Y ${f.cagr5y ?? "n/a"}%`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} style={{ display: "block" }}>
      <line x1="0" x2={w} y1={z} y2={z} stroke={C.line} strokeWidth="1" />
      {vals.map((v, i) => {
        const x = gap + i * (bw + gap);
        if (v == null) return <rect key={i} x={x} y={z - 1} width={bw} height="2" fill={C.line} />;
        const yy = y(v);
        return <rect key={i} x={x} y={Math.min(yy, z)} width={bw} height={Math.max(1.5, Math.abs(z - yy))} rx="2" fill={v >= 0 ? C.pos : C.neg} opacity={i === 0 ? 1 : 0.75} />;
      })}
    </svg>
  );
}

export function CompareToggle({ id, compare, onToggle }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 600, color: C.ink2, cursor: "pointer", userSelect: "none" }}>
      <input type="checkbox" checked={compare.has(id)} onChange={() => onToggle(id)} style={{ width: 17, height: 17, accentColor: C.accent, cursor: "pointer" }} />
      Compare
    </label>
  );
}

export function Kpi({ label, value, sub }) {
  return (
    <div style={{ padding: "12px 14px", background: C.surface2, border: `1px solid ${C.line}`, borderRadius: 12, minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: C.faint }}>{label}</div>
      <div className="num" style={{ fontSize: 19, fontWeight: 700, marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: C.faint, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>}
    </div>
  );
}

export function SectionHead({ id, title, sub, meta, children }) {
  return (
    <div id={id} style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: "10px 20px", scrollMarginTop: 90 }}>
      <div>
        <h2 style={{ fontSize: 21, fontWeight: 800, margin: 0 }}>{title}</h2>
        {sub && <p style={{ margin: "4px 0 0", color: C.muted, fontSize: 13.5 }}>{sub}</p>}
      </div>
      {meta && <span style={{ fontSize: 12, color: C.faint }}>{meta}</span>}
      {children}
    </div>
  );
}

export const selectStyle = { height: 36, border: `1px solid ${C.line}`, borderRadius: 9, background: "#FFFFFF", color: C.ink, padding: "0 10px", fontFamily: "inherit", fontSize: 13, fontWeight: 600 };

export const th = { height: 38, padding: "0 12px", textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: C.faint, background: C.surface2, borderBottom: `1px solid ${C.line}`, whiteSpace: "nowrap" };
export const td = { padding: "10px 12px", borderTop: `1px solid ${C.line2}`, fontSize: 13, verticalAlign: "middle" };

export const SORTS = [
  { key: "aumCr", label: "AUM (high to low)" },
  { key: "return1y", label: "1Y return" },
  { key: "cagr3y", label: "3Y CAGR" },
  { key: "cagr5y", label: "5Y CAGR" },
  { key: "expenseRatio", label: "Expense ratio (low to high)" },
];

export function sortFunds(list, key) {
  return [...list].sort((a, b) => {
    if (key === "expenseRatio") return a.expenseRatio - b.expenseRatio;
    return (b[key] ?? -99) - (a[key] ?? -99);
  });
}
