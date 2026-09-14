import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { useChartPreview } from "../chart/ChartPreviewContext";

// Ported from templates/scanner.html + static/js/scanner.js. The chart-
// preview modal that used to be duplicated inline in scanner.js now comes
// from the shared useChartPreview() hook instead (see the rewrite plan's
// note on that duplication) — everything else is a faithful port of the
// original's behavior: selecting a scanner loads its last cached result
// (never triggers a live run), "Run Scan" hits the live backend.

function isNumericType(type) {
  return type === "num" || type === "pct";
}

function Cell({ col, row, onSymbolClick }) {
  const value = row[col.key];
  if (value === null || value === undefined || value === "") return <span className="dim">-</span>;

  if (col.type === "bool") {
    return value ? <span className="badge">YES</span> : <span className="dim">No</span>;
  }
  if (col.type === "symbol") {
    const symbol = String(value).trim();
    return (
      <a
        className="symbol-link"
        href={`/markets/chart?symbol=${encodeURIComponent(symbol)}`}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => {
          e.preventDefault();
          onSymbolClick(symbol);
        }}
      >
        {symbol}
      </a>
    );
  }
  if (col.type === "pct") {
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value);
    return (
      <span className={num >= 0 ? "up" : "down"}>
        {num >= 0 ? "+" : ""}
        {num.toFixed(2)}%
      </span>
    );
  }
  if (col.type === "num") {
    const n = Number(value);
    return Number.isFinite(n) ? <span className="num">{n.toLocaleString("en-IN")}</span> : String(value);
  }
  return String(value);
}

export default function Scanner() {
  const [searchParams] = useSearchParams();
  const { openPreview } = useChartPreview();

  const [scanners, setScanners] = useState([]);
  const [selectedId, setSelectedId] = useState(searchParams.get("id") || "");
  const [status, setStatus] = useState({ text: "", mode: "" });
  const [stats, setStats] = useState([]);
  const [columns, setColumns] = useState([]);
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState("");
  const [running, setRunning] = useState(false);

  useEffect(() => {
    apiFetch("/api/scanners")
      .then((res) => res.json())
      .then((data) => {
        setScanners(data);
        // If the initial ?id= isn't a real scanner, fall back to none
        // selected — same validation scanner_page() did server-side.
        if (!data.some((s) => s.id === selectedId)) setSelectedId("");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount, mirroring the old server-rendered bootstrap
  }, []);

  useEffect(() => {
    setStatus({ text: "", mode: "" });
    setStats([]);
    setColumns([]);
    setRows([]);
    setMeta("");
    if (!selectedId) return;

    apiFetch(`/api/scanners/${encodeURIComponent(selectedId)}/cached`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.cached) return;
        setStats(data.stats || []);
        setColumns(data.columns || []);
        setRows(data.rows || []);
        setMeta(`Cached result from ${data.generated_at} — click Run Scan to refresh`);
      })
      .catch(() => {});
  }, [selectedId]);

  function runScanner() {
    if (!selectedId) return;
    setRunning(true);
    setStatus({ text: "Running scanner on the backend — this can take a few seconds…", mode: "loading" });
    setStats([]);
    setColumns([]);
    setRows([]);
    setMeta("");

    apiFetch(`/api/scanners/${encodeURIComponent(selectedId)}/run`)
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        const data = result.data;
        if (!result.ok || data.error) {
          setStatus({ text: `Error: ${data.error || "Unknown error"}`, mode: "error" });
          return;
        }
        setStatus({ text: "", mode: "" });
        setStats(data.stats || []);
        setColumns(data.columns || []);
        setRows(data.rows || []);
        setMeta(`Generated ${data.generated_at}`);
      })
      .catch((err) => {
        setStatus({ text: `Request failed: ${err.message}`, mode: "error" });
      })
      .finally(() => setRunning(false));
  }

  const selectedScanner = scanners.find((s) => s.id === selectedId);

  return (
    <div style={{ width: "100%", padding: "32px 48px 56px" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 22, gap: 16, flexWrap: "wrap" }}>
          <div>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Scanner</span>
            <h1 style={{ fontSize: 28, fontWeight: 800, marginTop: 6 }}>Screener console</h1>
            <p style={{ fontSize: 13.5, color: "#5B6270", margin: "8px 0 0", maxWidth: 560 }}>
              Pick a scanner — each one calls its backend Python code live and renders the result below.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, border: "1.5px solid #D8DAE3", borderRadius: 10, padding: "9px 14px" }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#17A673" }} />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: "#5B6270" }}>Live scan</span>
          </div>
        </div>

        <div className="scanner-layout">
          <div className="sidebar">
            <span className="sidebar-title">Scanners</span>
            <div className="scanner-list">
              {scanners.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={"scanner-option" + (s.id === selectedId ? " selected" : "")}
                  onClick={() => setSelectedId(s.id)}
                >
                  {s.name}
                </button>
              ))}
            </div>
            <p className="scanner-desc">{selectedScanner ? selectedScanner.description : ""}</p>
            <button id="runBtn" type="button" className="run-btn" onClick={runScanner} disabled={running || !selectedId}>
              Run Scan
            </button>
          </div>

          <div className="results-panel">
            <div className="results-head">
              <p className={"status" + (status.mode ? " " + status.mode : "")}>{status.text}</p>
              <p className="meta" style={{ padding: 0 }}>{meta}</p>
            </div>
            <div className="stats">
              {stats.map((s, i) => (
                <div className="stat" key={i}>
                  <div className="value">{s.value}</div>
                  <div className="label">{s.label}</div>
                </div>
              ))}
            </div>
            <div>
              {!columns.length ? null : !rows.length ? (
                <div className="empty">No matches</div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {columns.map((c) => (
                          <th key={c.key} className={isNumericType(c.type) ? "num" : ""}>
                            {c.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={i}>
                          {columns.map((c) => (
                            <td key={c.key} className={isNumericType(c.type) ? "num" : ""}>
                              <Cell col={c} row={row} onSymbolClick={openPreview} />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
