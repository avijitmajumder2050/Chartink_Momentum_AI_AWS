import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";

// Dhan super orders placed by trading-bot-algo from Quantile breakout
// winners — GET /api/admin/quantile-orders (app.py) merges each
// quantile-order-intents row with its live super order (entry leg,
// STOP_LOSS_LEG, TARGET_LEG). Auto-refreshes while any trade is open.
const REFRESH_MS = 30000;

const STATE_STYLE = {
  active: { label: "Active", color: "#17A673", background: "#E6F7F1" },
  entry_pending: { label: "Entry pending", color: "#4640DE", background: "#ECEBFC" },
  queued: { label: "Queued", color: "#4640DE", background: "#ECEBFC" },
  placing: { label: "Placing", color: "#4640DE", background: "#ECEBFC" },
  closed: { label: "Closed", color: "#5B6270", background: "#F0F1F4" },
  paper: { label: "Paper", color: "#B98A2E", background: "#FBF2E1" },
  rejected: { label: "Rejected", color: "#E0473F", background: "#FCEBEA" },
  cancelled: { label: "Cancelled", color: "#E0473F", background: "#FCEBEA" },
  expired: { label: "Expired", color: "#E0473F", background: "#FCEBEA" },
  failed: { label: "Failed", color: "#E0473F", background: "#FCEBEA" },
  no_result: { label: "No result", color: "#B98A2E", background: "#FBF2E1" },
};
const DEFAULT_STATE_STYLE = { label: "Unknown", color: "#5B6270", background: "#F0F1F4" };

const REASON_STYLE = {
  Target: { color: "#17A673" },
  "Trailing SL": { color: "#B98A2E" },
  SL: { color: "#E0473F" },
};

const OPEN_STATES = new Set(["active", "entry_pending", "queued", "placing"]);

const PAGE_SIZES = [10, 25, 50, 100];
const PAGE_SIZE_KEY = "quantileOrders.pageSize";

function loadPageSize() {
  try {
    const saved = Number(localStorage.getItem(PAGE_SIZE_KEY));
    return PAGE_SIZES.includes(saved) ? saved : 10;
  } catch {
    return 10;
  }
}

const pagerButton = (disabled) => ({
  border: "1px solid #E3E6EC", background: "#FFFFFF", color: disabled ? "#C5C9D3" : "#14171F", cursor: disabled ? "default" : "pointer",
  fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "6px 12px", borderRadius: 8,
});

const money = (v) => (v === null || v === undefined ? "—" : `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
const pnlColor = (v) => (v > 0 ? "#17A673" : v < 0 ? "#E0473F" : "#5B6270");
const signedMoney = (v) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`);

function formatTime(iso) {
  if (!iso) return "—";
  // created_at is naive UTC from datetime.utcnow(); Dhan's times are already IST strings.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) || iso.includes(" ") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
}

function Stat({ label, value, color }) {
  return (
    <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: "14px 18px", minWidth: 150, flex: "1 1 150px" }}>
      <span style={{ fontSize: 11, color: "#8A90A0", textTransform: "uppercase" }}>{label}</span>
      <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4, color: color || "#14171F" }}>{value}</div>
    </div>
  );
}

const cell = { padding: "12px 14px", fontSize: 13, whiteSpace: "nowrap" };
const mono = { ...cell, fontFamily: "'IBM Plex Mono', monospace" };

export default function AdminQuantileOrders() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [filter, setFilter] = useState("all");
  const [pageSize, setPageSize] = useState(loadPageSize);
  const [page, setPage] = useState(1);

  const changePageSize = (size) => {
    setPageSize(size);
    setPage(1);
    try {
      localStorage.setItem(PAGE_SIZE_KEY, String(size));
    } catch {
      // storage blocked — the choice just won't be remembered
    }
  };

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = () => {
      apiFetch("/api/admin/quantile-orders")
        .then((res) => {
          if (!res.ok) throw new Error(res.status);
          return res.json();
        })
        .then((d) => {
          if (cancelled) return;
          setData(d);
          setError(false);
          if (d.orders.some((o) => OPEN_STATES.has(o.state))) timer = setTimeout(load, REFRESH_MS);
        })
        .catch(() => !cancelled && setError(true));
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [retryCount]);

  if (error && !data) {
    return (
      <div style={{ padding: "60px 36px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>Couldn't load orders right now.</p>
        <button
          type="button"
          onClick={() => setRetryCount((c) => c + 1)}
          style={{ background: "#4640DE", color: "white", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "10px 20px", borderRadius: 9 }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (data === null) return null;

  const orders = data.orders;
  const activeCount = orders.filter((o) => OPEN_STATES.has(o.state)).length;
  const closed = orders.filter((o) => o.state === "closed");
  const realised = closed.reduce((sum, o) => sum + (o.pnl || 0), 0);
  const unrealised = orders.filter((o) => o.state === "active").reduce((sum, o) => sum + (o.pnl || 0), 0);
  const wins = closed.filter((o) => o.pnl > 0).length;

  const filtered = orders.filter((o) => (filter === "all" ? true : filter === "open" ? OPEN_STATES.has(o.state) : !OPEN_STATES.has(o.state)));
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  // Clamped rather than reset in an effect — an auto-refresh that shrinks
  // the list just lands on the new last page.
  const currentPage = Math.min(page, pageCount);
  const firstIndex = (currentPage - 1) * pageSize;
  const visible = filtered.slice(firstIndex, firstIndex + pageSize);

  return (
    <div style={{ padding: "30px clamp(16px, 4vw, 36px) 60px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12, marginBottom: 22 }}>
        <div>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>{orders.length} auto-orders from breakout winners</span>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginTop: 2 }}>Quantile Orders</h1>
          <p style={{ fontSize: 13, color: "#5B6270", marginTop: 6 }}>Dhan super orders — entry, stop-loss, trailing stop and target. {activeCount ? "Refreshing every 30s while a trade is open." : ""}</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[["all", "All"], ["open", "Open"], ["done", "Closed"]].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setFilter(key);
                setPage(1);
              }}
              style={{
                border: "1px solid #E3E6EC", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "8px 14px", borderRadius: 9,
                background: filter === key ? "#14171F" : "#FFFFFF", color: filter === key ? "#FFFFFF" : "#5B6270",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {data.dhan_error && (
        <div style={{ background: "#FCEBEA", color: "#E0473F", borderRadius: 10, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>
          Couldn't reach Dhan's super order book — showing the last saved state. ({data.dhan_error})
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
        <Stat label="Open trades" value={activeCount} />
        <Stat label="Unrealised P&L" value={signedMoney(unrealised)} color={pnlColor(unrealised)} />
        <Stat label="Realised P&L" value={signedMoney(realised)} color={pnlColor(realised)} />
        <Stat label="Win rate" value={closed.length ? `${Math.round((wins / closed.length) * 100)}% (${wins}/${closed.length})` : "—"} />
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
        <div className="table-wrap">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
                {["Stock", "Status", "Qty", "Entry", "SL (orig → now)", "Trail pts", "Target", "LTP / Exit", "P&L", "Close reason", "Order ID"].map((h) => (
                  <th key={h} style={{ padding: "12px 14px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: "left", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!visible.length ? (
                <tr><td colSpan={11} style={{ padding: "30px 16px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>No orders here yet.</td></tr>
              ) : (
                visible.map((o) => {
                  const st = STATE_STYLE[o.state] || DEFAULT_STATE_STYLE;
                  const trailed = o.current_sl !== null && o.original_sl !== null && Math.abs(o.current_sl - o.original_sl) > 0.01;
                  const isClosed = o.state === "closed";
                  return (
                    <tr key={o.entry_id} style={{ borderBottom: "1px solid #F0F1F4" }}>
                      <td style={cell}>
                        <span style={{ fontWeight: 700 }}>{o.symbol}</span>
                        <span style={{ fontSize: 11, color: "#8A90A0", display: "block" }}>{o.side} · {formatTime(o.created_at)}</span>
                      </td>
                      <td style={cell}>
                        <span title={o.dhan_status || ""} style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: 100, color: st.color, background: st.background }}>{st.label}</span>
                        {o.error && <span style={{ fontSize: 11, color: "#E0473F", display: "block", marginTop: 4, whiteSpace: "normal", maxWidth: 200 }}>{o.error}</span>}
                      </td>
                      <td style={mono}>{o.qty ?? "—"}</td>
                      <td style={mono}>{money(o.entry_price)}</td>
                      <td style={mono}>
                        {money(o.original_sl)}
                        {trailed && <span style={{ color: "#B98A2E" }}> → {money(o.current_sl)}</span>}
                      </td>
                      <td style={mono}>{o.trailing_jump ?? "—"}</td>
                      <td style={mono}>{money(o.target_price)}</td>
                      <td style={mono}>
                        {isClosed ? money(o.exit_price) : money(o.ltp)}
                        {isClosed && o.exit_time && <span style={{ fontSize: 11, color: "#8A90A0", display: "block" }}>{o.exit_time.slice(11, 16)}</span>}
                      </td>
                      <td style={{ ...mono, fontWeight: 700, color: pnlColor(o.pnl) }}>{signedMoney(o.pnl)}</td>
                      <td style={{ ...cell, fontWeight: 700, ...(REASON_STYLE[o.close_reason] || { color: "#5B6270" }) }}>{isClosed ? o.close_reason || "—" : "—"}</td>
                      <td style={{ ...cell, fontSize: 12, color: "#8A90A0" }}>{o.order_id || "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {filtered.length > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, padding: "12px 14px", borderTop: "1px solid #E3E6EC" }}>
            <label style={{ fontSize: 12.5, color: "#5B6270", display: "flex", alignItems: "center", gap: 8 }}>
              Rows per page
              <select
                value={pageSize}
                onChange={(e) => changePageSize(Number(e.target.value))}
                style={{ fontFamily: "inherit", fontSize: 12.5, fontWeight: 700, padding: "5px 8px", borderRadius: 8, border: "1px solid #E3E6EC", background: "#FFFFFF", color: "#14171F" }}
              >
                {PAGE_SIZES.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12.5, color: "#5B6270" }}>
                {firstIndex + 1}–{firstIndex + visible.length} of {filtered.length}
              </span>
              <button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)} style={pagerButton(currentPage === 1)} aria-label="Previous page">
                ‹ Prev
              </button>
              <span style={{ fontSize: 12.5, fontWeight: 700 }}>
                {currentPage} / {pageCount}
              </span>
              <button type="button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)} style={pagerButton(currentPage === pageCount)} aria-label="Next page">
                Next ›
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
