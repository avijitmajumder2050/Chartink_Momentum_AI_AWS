import { useState } from "react";

// Extra Research-page sections. Everything except the filings comes from
// the same screener.in page the rest of Research already scrapes
// (fundamentals_connector) — no additional requests. Filings come from
// NSE's per-company announcements (news_connector.get_stock_filings).

const GREEN = "#17A673";
const RED = "#E0473F";
const card = { background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 };
const heading = { fontSize: 14.5, fontWeight: 700, display: "block", marginBottom: 12 };
const muted = { fontSize: 11.5, color: "#8A90A0" };

function timeAgo(iso) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

const pctNum = (s) => {
  const n = parseFloat(String(s).replace("%", ""));
  return Number.isFinite(n) ? n : null;
};

// ---- Strengths & concerns + compounded growth -----------------------
export function AnalysisCard({ pros = [], cons = [], growth = [] }) {
  if (!pros.length && !cons.length && !growth.length) return null;
  return (
    <div style={card}>
      <span style={heading}>Strengths &amp; concerns</span>
      {(pros.length > 0 || cons.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginBottom: growth.length ? 20 : 0 }}>
          {[["Strengths", pros, GREEN, "#E6F7F1", "+"], ["Concerns", cons, RED, "#FCEBEA", "−"]].map(([title, items, color, bg, glyph]) => (
            <div key={title} style={{ background: bg, borderRadius: 12, padding: "14px 16px" }}>
              <span style={{ fontSize: 12.5, fontWeight: 800, color, display: "block", marginBottom: 8 }}>{title}</span>
              {!items.length ? (
                <span style={{ fontSize: 12.5, color: "#5B6270" }}>None flagged.</span>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 7 }}>
                  {items.map((t) => (
                    <li key={t} style={{ display: "flex", gap: 8, fontSize: 13, color: "#33374A", lineHeight: 1.5 }}>
                      <span aria-hidden="true" style={{ color, fontWeight: 800 }}>{glyph}</span>
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {growth.length > 0 && (
        <>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: "#5B6270", display: "block", marginBottom: 8 }}>Compounded growth</span>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  {growth[0].values.map((v) => (
                    <th key={v.period} className="num">{v.period.replace(" Years", "Y").replace("Last Year", "Last yr").replace("1 Year", "1Y")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {growth.map((g) => (
                  <tr key={g.title}>
                    <td style={{ fontWeight: 600 }}>{g.title.replace("Compounded ", "")}</td>
                    {g.values.map((v) => {
                      const n = pctNum(v.value);
                      return (
                        <td key={v.period} className="num" style={{ fontWeight: 700, color: n == null ? "#8A90A0" : n < 0 ? RED : n >= 15 ? GREEN : "#14171F" }}>
                          {v.value || "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p style={{ ...muted, margin: "12px 0 0" }}>Via screener.in. Strengths &amp; concerns are rule-based flags, not advice.</p>
    </div>
  );
}

// ---- About + industry -----------------------------------------------
export function AboutCard({ about, keyPoints, industry = [] }) {
  const [open, setOpen] = useState(false);
  if (!about && !keyPoints && !industry.length) return null;
  return (
    <div style={card}>
      <span style={heading}>About the company</span>
      {industry.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginBottom: 12 }} aria-label="Industry classification">
          {industry.map((lvl, i) => (
            <span key={lvl.level} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {i > 0 && <span aria-hidden="true" style={{ color: "#C5C9D2" }}>›</span>}
              <span title={lvl.level} style={{ fontSize: 11.5, fontWeight: 700, color: i === industry.length - 1 ? "#4640DE" : "#5B6270", background: i === industry.length - 1 ? "#EEEDFD" : "#F0F1F4", padding: "3px 8px", borderRadius: 100 }}>{lvl.label}</span>
            </span>
          ))}
        </div>
      )}
      {about && <p style={{ fontSize: 13, color: "#33374A", lineHeight: 1.65, margin: 0 }}>{about}</p>}
      {keyPoints && (
        <>
          {open && <p style={{ fontSize: 13, color: "#5B6270", lineHeight: 1.65, margin: "10px 0 0" }}>{keyPoints}</p>}
          <button type="button" onClick={() => setOpen((v) => !v)} style={{ background: "none", border: "none", padding: 0, marginTop: 8, cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, color: "#4640DE" }}>
            {open ? "Show less" : "Key points ›"}
          </button>
        </>
      )}
    </div>
  );
}

// ---- Working-capital efficiency -------------------------------------
export function EfficiencyCard({ rows = [] }) {
  if (!rows.length) return null;
  return (
    <div style={card}>
      <span style={heading}>Efficiency <span style={{ ...muted, fontWeight: 500 }}>(days, {rows[0].year.replace(/^Mar (\d{2})(\d{2})$/, "FY$2")})</span></span>
      {rows.map((r) => {
        // Fewer days is better for everything except Days Payable.
        const better = r.change == null ? null : r.label === "Days Payable" ? r.change > 0 : r.change < 0;
        return (
          <div key={r.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderTop: "1px solid #F0F1F4" }}>
            <span style={{ fontSize: 12.5, color: "#5B6270" }}>{r.label}</span>
            <span style={{ display: "inline-flex", alignItems: "baseline", gap: 8 }}>
              {r.change != null && r.change !== 0 && (
                <span style={{ fontSize: 11, fontWeight: 700, color: better ? GREEN : RED }} title={`Previous year: ${r.previous}`}>
                  {r.change > 0 ? "▲" : "▼"} {Math.abs(r.change)}
                </span>
              )}
              <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>{r.value}</span>
            </span>
          </div>
        );
      })}
      <p style={{ ...muted, margin: "10px 0 0" }}>Arrow = change vs the previous year; green is an improvement.</p>
    </div>
  );
}

// ---- Shareholding trend ---------------------------------------------
export function ShareholdingTrend({ trend }) {
  if (!trend?.rows?.length) return null;
  const first = trend.quarters[0];
  const last = trend.quarters[trend.quarters.length - 1];
  const holders = trend.shareholders;
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid #F0F1F4" }}>
      <span style={{ fontSize: 12.5, fontWeight: 700, color: "#5B6270", display: "block", marginBottom: 8 }}>
        Change {first} → {last}
      </span>
      {trend.rows.map((r) => (
        <div key={r.label} style={{ display: "grid", gridTemplateColumns: "84px 1fr auto", alignItems: "center", gap: 10, padding: "5px 0" }}>
          <span style={{ fontSize: 12.5, color: "#5B6270" }}>{r.label}</span>
          <svg width="100%" height="22" viewBox="0 0 260 32" preserveAspectRatio="none" aria-hidden="true">
            <polyline points={r.points} fill="none" stroke={r.color === "#D8DAE3" ? "#8A90A0" : r.color} strokeWidth="2.5" />
          </svg>
          <span className="num" style={{ fontSize: 12, fontWeight: 700, minWidth: 64, textAlign: "right", color: r.change > 0 ? GREEN : r.change < 0 ? RED : "#8A90A0" }}>
            {r.change > 0 ? "▲ +" : r.change < 0 ? "▼ " : ""}
            {r.change.toFixed(2)} pts
          </span>
        </div>
      ))}
      {holders && (
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 12 }}>
          <span style={{ color: "#5B6270" }}>No. of shareholders</span>
          <span className="num" style={{ fontWeight: 700 }}>
            {holders.values[holders.values.length - 1]}
            {holders.change != null && holders.change !== 0 && (
              <span style={{ color: "#8A90A0", fontWeight: 600 }}> ({holders.change > 0 ? "+" : "−"}{Math.abs(holders.change).toLocaleString("en-IN")})</span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

// ---- Filings & order wins -------------------------------------------
export function FilingsCard({ filings, orderWinNews = [], fallback = [] }) {
  const official = filings ?? null;
  const hasAny = (official && official.length) || orderWinNews.length || fallback.length;
  if (!hasAny) {
    return (
      <div style={card}>
        <span style={heading}>Recent filings &amp; order wins</span>
        <p style={{ fontSize: 13, color: "#8A90A0", margin: 0 }}>No exchange filings in the last 30 days.</p>
      </div>
    );
  }
  const orderWins = (official || []).filter((f) => f.orderWin);
  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <span style={{ fontSize: 14.5, fontWeight: 700 }}>Recent filings &amp; order wins</span>
        {orderWins.length > 0 && (
          <span style={{ fontSize: 11.5, fontWeight: 800, color: GREEN, background: "#E6F7F1", padding: "3px 9px", borderRadius: 100 }}>
            {orderWins.length} order {orderWins.length === 1 ? "win" : "wins"} in 30 days
          </span>
        )}
      </div>

      {orderWinNews.length > 0 && (
        <div style={{ background: "#F3FBF8", border: "1px solid #CDEFE2", borderRadius: 12, padding: "10px 14px", marginBottom: 12 }}>
          <span style={{ fontSize: 12, fontWeight: 800, color: GREEN, display: "block", marginBottom: 4 }}>Order wins in the news</span>
          {orderWinNews.map((n) => (
            <a key={n.link || n.headline} href={n.link} target="_blank" rel="noopener noreferrer" style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "6px 0", color: "#14171F", textDecoration: "none", fontSize: 13 }}>
              <span>
                {n.headline} <span style={muted}>· {n.source}</span>
              </span>
              {n.orderValue && <span className="num" style={{ fontWeight: 800, color: GREEN, whiteSpace: "nowrap" }}>{n.orderValue}</span>}
            </a>
          ))}
        </div>
      )}

      {official && official.length > 0
        ? official.map((f, i) => (
            <a
              key={`${f.publishedAt}-${i}`}
              href={f.link || undefined}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "grid", gridTemplateColumns: "72px 1fr", gap: 10, padding: "9px 0", borderTop: "1px solid #F0F1F4", color: "inherit", textDecoration: "none" }}
            >
              <span style={{ ...muted, paddingTop: 1 }}>{timeAgo(f.publishedAt)}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: f.orderWin ? GREEN : "#14171F" }}>
                  {f.orderWin && <span aria-hidden="true">● </span>}
                  {f.category || "Announcement"}
                </span>
                {f.detail && <span style={{ display: "block", fontSize: 12, color: "#5B6270", lineHeight: 1.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.detail}</span>}
              </span>
            </a>
          ))
        : fallback.map((a) => (
            <a key={a.url} href={a.url} target="_blank" rel="noopener noreferrer" style={{ display: "block", padding: "9px 0", borderTop: "1px solid #F0F1F4", fontSize: 13, color: "#14171F", textDecoration: "none" }}>
              {a.label}
            </a>
          ))}
      <p style={{ ...muted, margin: "10px 0 0" }}>{official ? "NSE announcements, last 30 days." : "BSE announcements via screener.in (NSE unavailable right now)."} Click to open the filing.</p>
    </div>
  );
}

// ---- Documents -------------------------------------------------------
export function DocumentsCard({ documents }) {
  const { concalls = [], annualReports = [], creditRatings = [] } = documents || {};
  if (!concalls.length && !annualReports.length && !creditRatings.length) return null;
  const link = { color: "#4640DE", fontWeight: 700, textDecoration: "none" };
  const chip = { fontSize: 11.5, fontWeight: 700, color: "#4640DE", background: "#EEEDFD", padding: "3px 9px", borderRadius: 100, textDecoration: "none" };
  return (
    <div style={card}>
      <span style={heading}>Documents</span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 18 }}>
        {concalls.length > 0 && (
          <div>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#5B6270", display: "block", marginBottom: 6 }}>Concalls</span>
            {concalls.map((c) => (
              <div key={c.period} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", flexWrap: "wrap" }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, width: 64 }}>{c.period}</span>
                {c.links.map((l) => (
                  <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" style={chip}>
                    {l.label === "REC" ? "Recording" : l.label}
                  </a>
                ))}
              </div>
            ))}
          </div>
        )}
        {annualReports.length > 0 && (
          <div>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#5B6270", display: "block", marginBottom: 6 }}>Annual reports</span>
            {annualReports.map((d) => (
              <a key={d.url} href={d.url} target="_blank" rel="noopener noreferrer" style={{ ...link, display: "block", fontSize: 12.5, padding: "6px 0" }}>
                {d.label.replace(/ from bse$/i, "")}
              </a>
            ))}
          </div>
        )}
        {creditRatings.length > 0 && (
          <div>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#5B6270", display: "block", marginBottom: 6 }}>Credit ratings</span>
            {creditRatings.map((d) => (
              <a key={d.url} href={d.url} target="_blank" rel="noopener noreferrer" style={{ ...link, display: "block", fontSize: 12.5, padding: "6px 0" }}>
                {d.label.replace(/^Rating update /i, "")}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

