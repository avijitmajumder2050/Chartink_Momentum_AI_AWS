import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import StockCard from "./StockCard";
import "@fortawesome/fontawesome-free/css/all.min.css";
import "./ChartWall.css";

// Ported from templates/chart_wall.html + its ~600-line inline script —
// the biggest/most interactive page in the app. New GET /api/watchlist
// (app.py) replaces the stock list that used to be baked into the
// server-rendered page. Choices.js (a 3rd-party imperative multi-select
// widget the original used for styling) is deliberately NOT ported —
// it's another imperative-DOM-ownership library fighting React the same
// way lightweight-charts does, and it's purely cosmetic; a plain native
// <select multiple> gives the same filtering behavior without that.

const fv = (v) => (v == null ? "—" : Number(v).toFixed(2));

function calcEMA(data, period) {
  if (!data || data.length === 0) return [];
  const multiplier = 2 / (period + 1);
  let ema = data[0].close;
  const result = [{ time: data[0].time, value: ema }];
  for (let i = 1; i < data.length; i++) {
    ema = (data[i].close - ema) * multiplier + ema;
    result.push({ time: data[i].time, value: Number(ema.toFixed(2)) });
  }
  return result;
}

// Same condition as dhan_ema_breakout.py's _compute_ema_signal(): close
// crosses above EMA10 or EMA20, with EMA10 > EMA20 > EMA50 aligned on
// the latest candle — kept identical so this filter and the "EMA 10/20
// Breakout" scanner agree on what a cross is.
function detectEmaCross(data) {
  if (!data || data.length < 50) return false;
  const ema10 = calcEMA(data, 10);
  const ema20 = calcEMA(data, 20);
  const ema50 = calcEMA(data, 50);
  const last = data.length - 1;
  const prev = last - 1;
  const latest = data[last];
  const previous = data[prev];
  const crossEma10 = previous.close <= ema10[prev].value && latest.close > ema10[last].value;
  const crossEma20 = previous.close <= ema20[prev].value && latest.close > ema20[last].value;
  const aligned = ema10[last].value > ema20[last].value && ema20[last].value > ema50[last].value;
  return (crossEma10 || crossEma20) && aligned;
}

function loadFavorites() {
  try {
    return JSON.parse(localStorage.getItem("cw_favs") || "{}");
  } catch {
    return {};
  }
}

export default function ChartWall() {
  const [allStocks, setAllStocks] = useState(null);
  const [unavailable, setUnavailable] = useState(false);

  const [search, setSearch] = useState("");
  const [selectedSetups, setSelectedSetups] = useState([]);
  const [rangeInputs, setRangeInputs] = useState({ epsMin: 0, epsMax: 100, psMin: 0, psMax: 100 });
  const [appliedRanges, setAppliedRanges] = useState({ epsMin: 0, epsMax: 100, psMin: 0, psMax: 100 });
  const [emaFilterOn, setEmaFilterOn] = useState(false);
  const [emaCrossCache, setEmaCrossCache] = useState({});
  const emaCrossLoaded = useRef(false);
  const [emaCrossLoading, setEmaCrossLoading] = useState(false);

  const [view, setView] = useState("card");
  const [layoutCols, setLayoutCols] = useState(2);
  const [pageSize, setPageSize] = useState(50);
  const [chartHeight, setChartHeight] = useState(440);
  const [page, setPage] = useState(1);
  const [darkMode, setDarkMode] = useState(false);
  const [favorites, setFavorites] = useState(loadFavorites);
  const [expandedSym, setExpandedSym] = useState(null);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [toast, setToastMsg] = useState(null);

  // Shared close/chg_pct/volume cache — populated as cards (card view) or
  // rows (table view) load, same role as the original's `tableData`.
  const [tableData, setTableData] = useState({});
  const toastTimer = useRef(null);

  function showToast(msg) {
    setToastMsg(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(null), 3000);
  }

  useEffect(() => {
    apiFetch("/api/watchlist")
      .then((res) => res.json())
      .then((data) => {
        setAllStocks(data.watchlist || []);
        setUnavailable(!!data.unavailable);
      })
      .catch(() => {
        setAllStocks([]);
        setUnavailable(true);
      });
  }, []);

  const setups = useMemo(() => {
    if (!allStocks) return [];
    return [...new Set(allStocks.map((s) => s.setupCase).filter(Boolean))].sort();
  }, [allStocks]);

  const handleData = useCallback((sym, row) => {
    setTableData((prev) => ({ ...prev, [sym]: row }));
    if (row.raw) setEmaCrossCache((prev) => (sym in prev ? prev : { ...prev, [sym]: detectEmaCross(row.raw) }));
  }, []);

  async function ensureEmaCrossLoaded() {
    if (emaCrossLoaded.current || emaCrossLoading || !allStocks) return;
    setEmaCrossLoading(true);
    showToast("Computing EMA cross for the watchlist in your browser — this fetches every stock's candles once…");

    const CONCURRENCY = 8;
    let idx = 0;
    const cache = {};
    const rows = {};
    async function worker() {
      while (idx < allStocks.length) {
        const stock = allStocks[idx++];
        try {
          const res = await apiFetch(`/api/chart/data?symbol=${encodeURIComponent(stock.symbol)}`);
          const d = await res.json();
          const raw = d.bars || [];
          if (raw.length) {
            const last = raw[raw.length - 1];
            const prev = raw[raw.length - 2];
            rows[stock.symbol] = { close: last.close, chg_pct: prev ? ((last.close - prev.close) / prev.close) * 100 : null, volume: last.volume };
            cache[stock.symbol] = detectEmaCross(raw);
          }
        } catch {
          cache[stock.symbol] = false;
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));

    setEmaCrossCache((prev) => ({ ...prev, ...cache }));
    setTableData((prev) => ({ ...rows, ...prev }));
    emaCrossLoaded.current = true;
    setEmaCrossLoading(false);
    showToast(`EMA cross ready — ${Object.values(cache).filter(Boolean).length} matches`);
  }

  useEffect(() => {
    if (emaFilterOn && !emaCrossLoaded.current) ensureEmaCrossLoaded();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per emaFilterOn toggle-on, not on every render
  }, [emaFilterOn]);

  const filteredStocks = useMemo(() => {
    if (!allStocks) return [];
    const q = search.toLowerCase().trim();
    return allStocks.filter((s) => {
      const mSearch = !q || s.symbol.toLowerCase().includes(q) || (s.setupCase || "").toLowerCase().includes(q);
      const mSetup = !selectedSetups.length || selectedSetups.includes(s.setupCase);
      const eps = s.epsStrength == null ? -1 : s.epsStrength;
      const ps = s.priceStrength == null ? -1 : s.priceStrength;
      const mEps = eps >= appliedRanges.epsMin && eps <= appliedRanges.epsMax;
      const mPs = ps >= appliedRanges.psMin && ps <= appliedRanges.psMax;
      const mEma = !emaFilterOn || emaCrossCache[s.symbol] === true;
      return mSearch && mSetup && mEps && mPs && mEma;
    });
  }, [allStocks, search, selectedSetups, appliedRanges, emaFilterOn, emaCrossCache]);

  useEffect(() => setPage(1), [search, selectedSetups, appliedRanges, emaFilterOn, view]);

  const totalPages = Math.max(1, Math.ceil(filteredStocks.length / pageSize));
  const clampedPage = Math.min(page, totalPages);
  const pageSlice = filteredStocks.slice((clampedPage - 1) * pageSize, clampedPage * pageSize);

  function toggleFavorite(sym) {
    setFavorites((prev) => {
      const next = { ...prev, [sym]: !prev[sym] };
      localStorage.setItem("cw_favs", JSON.stringify(next));
      return next;
    });
  }

  function toggleExpand(sym) {
    setExpandedSym((prev) => (prev === sym ? null : sym));
  }

  function resetFilters() {
    setSearch("");
    setSelectedSetups([]);
    setRangeInputs({ epsMin: 0, epsMax: 100, psMin: 0, psMax: 100 });
    setAppliedRanges({ epsMin: 0, epsMax: 100, psMin: 0, psMax: 100 });
    setEmaFilterOn(false);
  }

  function applyRanges() {
    setAppliedRanges({
      epsMin: Number(rangeInputs.epsMin) || 0,
      epsMax: Number.isFinite(Number(rangeInputs.epsMax)) ? Number(rangeInputs.epsMax) : 100,
      psMin: Number(rangeInputs.psMin) || 0,
      psMax: Number.isFinite(Number(rangeInputs.psMax)) ? Number(rangeInputs.psMax) : 100,
    });
  }

  function reloadVisible() {
    setTableData({});
    showToast("Reloaded visible charts");
  }

  function sortTable(key) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sortedTableRows = useMemo(() => {
    const rows = [...pageSlice];
    if (!sortKey) return rows;
    rows.sort((a, b) => {
      const va = tableData[a.symbol]?.[sortKey] ?? a[sortKey] ?? 0;
      const vb = tableData[b.symbol]?.[sortKey] ?? b[sortKey] ?? 0;
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return rows;
  }, [pageSlice, sortKey, sortDir, tableData]);

  // Lazily fetches price/change for table rows not yet in the cache —
  // same "fetch on render, cache in tableData" behavior as renderTable().
  useEffect(() => {
    if (view !== "table") return;
    sortedTableRows.forEach((s) => {
      if (tableData[s.symbol]) return;
      apiFetch(`/api/chart/data?symbol=${encodeURIComponent(s.symbol)}`)
        .then((res) => res.json())
        .then((d) => {
          const raw = d.bars || [];
          if (!raw.length) return;
          const last = raw[raw.length - 1];
          const prev = raw[raw.length - 2];
          const chg = prev ? ((last.close - prev.close) / prev.close) * 100 : null;
          handleData(s.symbol, { close: last.close, chg_pct: chg != null ? parseFloat(chg.toFixed(2)) : null, volume: last.volume, raw });
        })
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when the visible page/view changes, not on every tableData update
  }, [view, sortedTableRows]);

  function pageButtons() {
    const from = Math.max(1, clampedPage - 2);
    const to = Math.min(totalPages, from + 4);
    const nums = [];
    for (let i = from; i <= to; i++) nums.push(i);
    return nums;
  }

  if (allStocks === null) return null;

  if (unavailable) {
    return (
      <div style={{ width: "100%", padding: "64px 48px" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
          <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Watchlist temporarily unavailable</h2>
          <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach the watchlist data source just now. Please try again shortly.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={"chart-wall-root" + (darkMode ? " dark-mode" : "")}>
      <div className="cw-controls">
        <div className="cw-search-wrap">
          <i className="fas fa-search" />
          <input className="cw-search-input" placeholder="Search symbol or setup…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>

        <select
          multiple
          className="cw-ctrl-select cw-setup-select"
          value={selectedSetups}
          onChange={(e) => setSelectedSetups(Array.from(e.target.selectedOptions, (o) => o.value))}
        >
          {setups.map((sc) => <option key={sc} value={sc}>{sc}</option>)}
        </select>

        <select className="cw-ctrl-select" title="Columns" value={layoutCols} onChange={(e) => setLayoutCols(Number(e.target.value))}>
          <option value={1}>1 column</option>
          <option value={2}>2 columns</option>
          <option value={3}>3 columns</option>
          <option value={4}>4 columns</option>
        </select>

        <select className="cw-ctrl-select" title="Stocks per page" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
          <option value={50}>50 / page</option>
          <option value={100}>100 / page</option>
          <option value={150}>150 / page</option>
          <option value={200}>200 / page</option>
          <option value={99999}>All on one page</option>
        </select>

        <select className="cw-ctrl-select" value={chartHeight} onChange={(e) => setChartHeight(Number(e.target.value))}>
          <option value={340}>Short (340px)</option>
          <option value={440}>Medium (440px)</option>
          <option value={560}>Tall (560px)</option>
        </select>

        <label className="cw-ema-label">
          <input type="checkbox" checked={emaFilterOn} onChange={(e) => setEmaFilterOn(e.target.checked)} />
          EMA Cross only {emaCrossLoading && <span>(loading…)</span>}
        </label>

        <div className="cw-view-toggle">
          <button className={"cw-view-btn" + (view === "card" ? " active" : "")} title="Card view" onClick={() => setView("card")}>
            <i className="fas fa-th-large" />
          </button>
          <button className={"cw-view-btn" + (view === "table" ? " active" : "")} title="Table view" onClick={() => setView("table")}>
            <i className="fas fa-table" />
          </button>
        </div>

        <button className="cw-ctrl-btn" onClick={reloadVisible}><i className="fas fa-sync-alt" /> Reload visible</button>
        <button className="cw-ctrl-btn" onClick={() => setDarkMode((d) => !d)}>{darkMode ? "☀️" : "🌙"}</button>

        <span className="cw-count-badge">{filteredStocks.length} stock{filteredStocks.length !== 1 ? "s" : ""}</span>
      </div>

      <div className="cw-range-row">
        <div className="cw-range-group">
          EPS Strength
          <input type="number" min="0" max="100" value={rangeInputs.epsMin} onChange={(e) => setRangeInputs((r) => ({ ...r, epsMin: e.target.value }))} /> –
          <input type="number" min="0" max="100" value={rangeInputs.epsMax} onChange={(e) => setRangeInputs((r) => ({ ...r, epsMax: e.target.value }))} />
        </div>
        <div className="cw-range-group">
          Price Strength
          <input type="number" min="0" max="100" value={rangeInputs.psMin} onChange={(e) => setRangeInputs((r) => ({ ...r, psMin: e.target.value }))} /> –
          <input type="number" min="0" max="100" value={rangeInputs.psMax} onChange={(e) => setRangeInputs((r) => ({ ...r, psMax: e.target.value }))} />
        </div>
        <button className="cw-ctrl-btn" style={{ height: 30 }} onClick={applyRanges}>Apply</button>
        <button className="cw-ctrl-btn" style={{ height: 30 }} onClick={resetFilters}>Reset filters</button>
      </div>

      {view === "card" ? (
        <div className="cw-card-grid" style={{ gridTemplateColumns: `repeat(${layoutCols}, 1fr)` }}>
          {!pageSlice.length ? (
            <div style={{ padding: 60, textAlign: "center", color: "var(--text-secondary)", gridColumn: "1/-1" }}>No stocks match your filters.</div>
          ) : (
            pageSlice.map((stock) => (
              <StockCard
                key={stock.symbol}
                stock={stock}
                chartHeight={chartHeight}
                darkMode={darkMode}
                isFavorite={!!favorites[stock.symbol]}
                onToggleFavorite={toggleFavorite}
                isExpanded={expandedSym === stock.symbol}
                onToggleExpand={toggleExpand}
                onData={handleData}
                tableRow={tableData[stock.symbol]}
              />
            ))
          )}
        </div>
      ) : (
        <div className="cw-tbl-wrap">
          <table className="cw-stock-table">
            <thead>
              <tr>
                <th className="sortable" onClick={() => sortTable("symbol")}>Symbol <span>{sortKey === "symbol" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span></th>
                <th>Setup</th>
                <th>EPS Str</th>
                <th>Price Str</th>
                <th className="sortable" onClick={() => sortTable("close")}>Close <span>{sortKey === "close" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span></th>
                <th className="sortable" onClick={() => sortTable("chg_pct")}>Change% <span>{sortKey === "chg_pct" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span></th>
                <th>Market Cap</th>
              </tr>
            </thead>
            <tbody>
              {!sortedTableRows.length ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: 30, color: "var(--text-secondary)" }}>No stocks found</td></tr>
              ) : (
                sortedTableRows.map((s) => {
                  const td = tableData[s.symbol] || {};
                  return (
                    <tr key={s.symbol}>
                      <td><b>{s.symbol}</b></td>
                      <td>{s.setupCase ? <span className="cw-tbl-setup">{s.setupCase}</span> : "—"}</td>
                      <td>{s.epsStrength ?? "—"}</td>
                      <td>{s.priceStrength ?? "—"}</td>
                      <td>{td.close != null ? fv(td.close) : "—"}</td>
                      <td style={{ color: (td.chg_pct || 0) >= 0 ? "var(--success)" : "var(--error)" }}>
                        {td.chg_pct != null ? (td.chg_pct >= 0 ? "▲" : "▼") + Math.abs(td.chg_pct).toFixed(2) + "%" : "—"}
                      </td>
                      <td>{s.marketCap ? Number(s.marketCap).toFixed(0) + " Cr" : "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="cw-pg-wrap">
        <button className="cw-pg-btn" disabled={clampedPage === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>‹ Prev</button>
        <div style={{ display: "flex", gap: 6 }}>
          {pageButtons().map((i) => (
            <button key={i} className={"cw-pg-btn" + (i === clampedPage ? " active" : "")} onClick={() => setPage(i)}>{i}</button>
          ))}
        </div>
        <button className="cw-pg-btn" disabled={clampedPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Next ›</button>
        <span className="cw-pg-info">
          {filteredStocks.length ? `${(clampedPage - 1) * pageSize + 1}–${Math.min(clampedPage * pageSize, filteredStocks.length)} of ${filteredStocks.length}` : "0 stocks"}
        </span>
      </div>

      {toast && <div id="cwToast" className="show">{toast}</div>}
    </div>
  );
}
