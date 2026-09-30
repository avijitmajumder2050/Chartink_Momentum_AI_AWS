import { C, CompareToggle, LockIn, Pct, TrendBars, aumText, card, inr, minText } from "./shared";

function Metric({ label, children, span }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, gridColumn: span }}>
      <span style={{ fontSize: 11, color: C.faint }}>{label}</span>
      <span style={{ fontSize: 13.5, fontWeight: 700 }}>{children}</span>
    </div>
  );
}

function Chip({ children, tone }) {
  const tones = {
    index: { bg: C.accent, color: "#fff" },
    mf: { bg: C.pos, color: "#fff" },
    plain: { bg: C.accentSoft, color: C.accent },
  };
  const t = tones[tone] || tones.plain;
  return <span style={{ display: "inline-flex", alignItems: "center", height: 22, padding: "0 9px", borderRadius: 11, fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", background: t.bg, color: t.color }}>{children}</span>;
}

function AumBox({ f, right, size = 21 }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "12px 14px", background: "#F7F8FA", border: `1px solid ${C.line}`, borderRadius: 11 }}>
      <div>
        <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: C.accent }}>
          AUM{f.aumDate && <span style={{ color: C.faint, fontWeight: 600, letterSpacing: 0, textTransform: "none" }}> · {f.aumDate}</span>}
        </div>
        <div className="num" style={{ fontSize: size, fontWeight: 700, whiteSpace: "nowrap" }}>{aumText(f.aumCr)}</div>
      </div>
      <div className="num" style={{ fontSize: 11, color: C.faint, textAlign: "right" }}>{right}</div>
    </div>
  );
}

const foot = { display: "flex", alignItems: "center", gap: 10, marginTop: "auto", flexWrap: "wrap" };
const viewBtn = { flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", height: 38, padding: "0 14px", borderRadius: 9, fontWeight: 700, fontSize: 13, textDecoration: "none", border: `1px solid ${C.line}`, color: C.ink, background: "#FFFFFF" };

export function IndexFundCard({ f, compare, onToggle }) {
  return (
    <article style={{ ...card, display: "flex", flexDirection: "column", gap: 14, padding: 20, minWidth: 0 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <Chip tone="index">Index Fund</Chip>
        {(f.capBadges || []).map((b) => (
          <Chip key={b}>{b}</Chip>
        ))}
      </div>
      <div>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>{f.amc}</span>
        <h3 style={{ fontSize: 16.5, lineHeight: 1.3, fontWeight: 800, margin: "2px 0 6px" }}>{f.name}</h3>
        <span style={{ fontSize: 12.5, color: C.muted }}>
          Tracks <b style={{ color: C.ink2 }}>{f.index}</b> · Direct Growth
        </span>
      </div>
      <AumBox f={f} right={<>NAV ₹{inr(f.nav)}<br />as of {f.dataDate}</>} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: "12px 10px" }}>
        <Metric label="1Y return"><Pct v={f.return1y} /></Metric>
        <Metric label="3Y CAGR"><Pct v={f.cagr3y} /></Metric>
        <Metric label="5Y CAGR"><Pct v={f.cagr5y} /></Metric>
        <Metric label="Expense ratio">
          <span className="num">{f.expenseRatio.toFixed(2)}%</span>
          {f.note && <span style={{ color: C.warn }}> †</span>}
        </Metric>
        <Metric label="Risk">{f.risk}</Metric>
        <Metric label="Launched"><span className="num">{f.launch || "—"}</span></Metric>
        <Metric label="Exit load" span="span 2"><span style={{ fontSize: 13, fontWeight: 600 }}>{f.exitLoad}</span></Metric>
        <Metric label="Lock-in"><LockIn f={f} /></Metric>
        <Metric label="Min lumpsum / SIP" span="1 / -1"><span className="num">{minText(f)}</span></Metric>
      </div>
      {f.note && <div style={{ fontSize: 11.5, color: C.warn, background: C.warnSoft, borderRadius: 8, padding: "7px 9px", lineHeight: 1.45 }}>† {f.note}</div>}
      <div style={foot}>
        <a href={f.url} target="_blank" rel="noopener noreferrer" style={viewBtn}>View details ↗</a>
        <CompareToggle id={f.id} compare={compare} onToggle={onToggle} />
      </div>
    </article>
  );
}

export function EquityFundCard({ f, rank, compare, onToggle }) {
  return (
    <article style={{ ...card, display: "flex", flexDirection: "column", gap: 14, padding: 20, minWidth: 0 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <Chip tone="mf">Equity MF</Chip>
        <Chip>{f.category}</Chip>
        <span style={{ marginLeft: "auto", fontSize: 11.5, fontWeight: 800, color: C.accent, background: C.accentSoft, borderRadius: 6, padding: "3px 8px", whiteSpace: "nowrap" }}>#{rank} by 5Y CAGR</span>
      </div>
      <div style={{ minHeight: 58 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>{f.amc}</span>
        <h3 style={{ fontSize: 15.5, lineHeight: 1.3, fontWeight: 800, margin: "2px 0 0" }}>{f.name}</h3>
      </div>
      <AumBox f={f} size={17} right={f.nav != null ? <>NAV ₹{inr(f.nav)}<br />{f.dataDate}</> : <>as of<br />{f.dataDate}</>} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: "12px 10px" }}>
        <Metric label="1Y return"><Pct v={f.return1y} /></Metric>
        <Metric label="3Y CAGR"><Pct v={f.cagr3y} /></Metric>
        <Metric label="5Y CAGR"><Pct v={f.cagr5y} /></Metric>
        <Metric label="Expense ratio"><span className="num">{f.expenseRatio.toFixed(2)}%</span></Metric>
        <Metric label="Risk">{f.risk}</Metric>
        <Metric label="Returns trend"><TrendBars f={f} /></Metric>
        <Metric label="Exit load" span="span 2"><span style={{ fontSize: 13, fontWeight: 600 }}>{f.exitLoad}</span></Metric>
        <Metric label="Lock-in"><LockIn f={f} /></Metric>
        <Metric label="Min lumpsum / SIP" span="1 / -1"><span className="num">{minText(f)}</span></Metric>
      </div>
      <div style={foot}>
        <a href={f.url} target="_blank" rel="noopener noreferrer" style={viewBtn}>View details ↗</a>
        <CompareToggle id={f.id} compare={compare} onToggle={onToggle} />
      </div>
    </article>
  );
}
