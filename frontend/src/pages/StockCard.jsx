import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode } from "lightweight-charts";
import { apiFetch } from "../api/client";

const EMA_COLORS = { 10: "#2962ff", 20: "#F2A93B", 50: "#aa00ff", 200: "#E0473F" };
const LEGEND_ITEMS = [
  { period: 10, label: "EMA 10" },
  { period: 20, label: "EMA 20" },
  { period: 50, label: "EMA 50" },
  { period: 200, label: "EMA200" },
];

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

const fv = (v) => (v == null ? "—" : Number(v).toFixed(2));

// One card = one independent lightweight-charts instance, mounted/torn
// down on this component's own lifecycle — same imperative-DOM-ownership
// pattern as ChartPreviewModal, just with more series (togglable EMA/
// volume legend) and a crosshair OHLC readout, ported from chart_wall.
// html's per-card loadChart()/buildCard() logic.
export default function StockCard({ stock, chartHeight, darkMode, isFavorite, onToggleFavorite, isExpanded, onToggleExpand, onData, tableRow }) {
  const mountRef = useRef(null);
  const ohlcRef = useRef(null);
  const chartRef = useRef(null); // {chart, candleSeries, emaSeries, volSeries}
  const [legendState, setLegendState] = useState({ 10: true, 20: true, 50: true, 200: true, volume: true });
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const sym = stock.symbol;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoaded(false);

    apiFetch(`/api/chart/data?symbol=${encodeURIComponent(sym)}`)
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (cancelled) return;
        const raw = data.bars || [];
        if (!ok || !raw.length) {
          setError((data && data.error) || "No data");
          return;
        }

        const last = raw[raw.length - 1];
        const prev = raw[raw.length - 2];
        const chgPct = prev ? ((last.close - prev.close) / prev.close) * 100 : null;
        onData(sym, { close: last.close, chg_pct: chgPct != null ? parseFloat(chgPct.toFixed(2)) : null, volume: last.volume, raw });

        const mount = mountRef.current;
        if (!mount) return;

        const chart = createChart(mount, {
          width: mount.clientWidth,
          height: chartHeight,
          layout: { background: { type: "solid", color: darkMode ? "#1e1e1e" : "#ffffff" }, textColor: darkMode ? "#cccccc" : "#333333", fontSize: 11 },
          grid: { vertLines: { color: darkMode ? "rgba(255,255,255,.04)" : "rgba(0,0,0,.04)" }, horzLines: { color: darkMode ? "rgba(255,255,255,.04)" : "rgba(0,0,0,.04)" } },
          crosshair: { mode: CrosshairMode.Normal },
          rightPriceScale: { borderColor: darkMode ? "#444" : "#ddd" },
          timeScale: { borderColor: darkMode ? "#444" : "#ddd", rightOffset: 6, barSpacing: 7 },
          handleScroll: true,
          handleScale: true,
        });

        const candleSeries = chart.addSeries(CandlestickSeries, {
          upColor: "#17A673", downColor: "#E0473F", borderVisible: false, wickUpColor: "#17A673", wickDownColor: "#E0473F",
        });
        candleSeries.setData(raw);

        const emaSeries = {};
        [10, 20, 50, 200].forEach((period) => {
          const series = chart.addSeries(LineSeries, { color: EMA_COLORS[period], lineWidth: period <= 20 ? 2 : 1, priceLineVisible: false, lastValueVisible: true });
          series.setData(calcEMA(raw, period));
          emaSeries[period] = series;
        });

        const volSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
        volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        volSeries.setData(raw.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(23,166,115,.45)" : "rgba(224,71,63,.45)" })));

        const volMap = {};
        raw.forEach((b) => { volMap[b.time] = b.volume; });
        chart.subscribeCrosshairMove((param) => {
          const ohlcEl = ohlcRef.current;
          if (!ohlcEl) return;
          if (!param || !param.time) { ohlcEl.textContent = "Hover over chart"; return; }
          const c = param.seriesData.get(candleSeries);
          if (!c) return;
          const vol = volMap[c.time] || 0;
          const volK = vol >= 1e6 ? (vol / 1e6).toFixed(1) + "M" : vol >= 1e3 ? (vol / 1e3).toFixed(0) + "K" : vol;
          const chgC = c.close >= c.open ? "#17A673" : "#E0473F";
          ohlcEl.innerHTML = `<b style="color:${chgC}">${c.close.toFixed(2)}</b> &nbsp;O:<b>${c.open.toFixed(2)}</b> H:<b>${c.high.toFixed(2)}</b> L:<b>${c.low.toFixed(2)}</b> V:<b>${volK}</b>`;
        });

        chart.timeScale().fitContent();
        const resizeObserver = new ResizeObserver((entries) => {
          if (chartRef.current?.chart !== chart) return;
          const entry = entries[0];
          if (entry) chart.applyOptions({ width: entry.contentRect.width });
        });
        resizeObserver.observe(mount);

        chartRef.current = { chart, candleSeries, emaSeries, volSeries, resizeObserver };
        setLoaded(true);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load");
      });

    return () => {
      cancelled = true;
      if (chartRef.current) {
        try { chartRef.current.resizeObserver.disconnect(); } catch { /* already gone */ }
        try { chartRef.current.chart.remove(); } catch { /* already gone */ }
        chartRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-fetch only when the symbol itself changes; height/theme are applied in place below
  }, [sym]);

  // Theme/height changes apply to the live chart instance instead of a
  // remount, matching the original's cwThemeBtn/cwChartHeight handlers.
  useEffect(() => {
    const inst = chartRef.current;
    if (!inst) return;
    const bg = darkMode ? "#1e1e1e" : "#ffffff";
    const tc = darkMode ? "#cccccc" : "#333333";
    const gc = darkMode ? "rgba(255,255,255,.04)" : "rgba(0,0,0,.04)";
    inst.chart.applyOptions({ layout: { background: { color: bg }, textColor: tc }, grid: { vertLines: { color: gc }, horzLines: { color: gc } } });
  }, [darkMode]);

  useEffect(() => {
    const inst = chartRef.current;
    if (!inst || isExpanded) return; // expanded height is handled by the expand effect below
    inst.chart.applyOptions({ height: chartHeight });
  }, [chartHeight, isExpanded]);

  useEffect(() => {
    const inst = chartRef.current;
    const mount = mountRef.current;
    if (!inst || !mount) return;
    const h = isExpanded ? window.innerHeight - 130 : chartHeight;
    const t = setTimeout(() => {
      inst.chart.applyOptions({ width: mount.clientWidth, height: h });
      inst.chart.timeScale().fitContent();
    }, 50);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run on expand/collapse, chartHeight already handled above
  }, [isExpanded]);

  function toggleLegend(key) {
    setLegendState((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      const inst = chartRef.current;
      if (inst) {
        if (key === "volume") inst.volSeries.applyOptions({ visible: next.volume });
        else inst.emaSeries[key]?.applyOptions({ visible: next[key] });
      }
      return next;
    });
  }

  async function downloadChart() {
    const inst = chartRef.current;
    if (!inst) return;
    try {
      const canvas = await inst.chart.takeScreenshot();
      const ctx = canvas.getContext("2d");
      ctx.font = "bold 28px Arial";
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.fillText(sym, 20, 40);
      const a = document.createElement("a");
      a.href = canvas.toDataURL("image/png");
      a.download = `chart_${sym}.png`;
      a.click();
    } catch { /* best-effort */ }
  }

  const chgClass = (tableRow?.chg_pct || 0) >= 0 ? "cw-chg-pos" : "cw-chg-neg";
  const chgStr = tableRow?.chg_pct != null ? (tableRow.chg_pct >= 0 ? "▲" : "▼") + Math.abs(tableRow.chg_pct).toFixed(2) + "%" : "";

  return (
    <div className={"cw-stock-card" + (isExpanded ? " expanded" : "")}>
      <div className="cw-card-header">
        <div className="cw-stock-meta">
          <span className="cw-stock-name">{sym}</span>
          {stock.setupCase && (
            <span className="cw-setup-badge">
              {stock.setupCase} | RS {stock.rsRating ?? "—"} | EPS {stock.epsStrength ?? "—"} | PS {stock.priceStrength ?? "—"}
            </span>
          )}
        </div>
        <div className="cw-price-wrap">
          <div className="cw-price-ltp">{tableRow?.close ? fv(tableRow.close) : "—"}</div>
          <div className={"cw-price-chg " + chgClass}>{chgStr}</div>
        </div>
        <div className="cw-card-actions">
          <button className={"cw-action-btn" + (isFavorite ? " fav-on" : "")} title="Favourite" onClick={() => onToggleFavorite(sym)}>
            <i className={(isFavorite ? "fas" : "far") + " fa-star"} />
          </button>
          <button className="cw-action-btn" title="Download PNG" onClick={downloadChart}>
            <i className="fas fa-download" />
          </button>
          <button className="cw-action-btn" title="Expand" onClick={() => onToggleExpand(sym)}>
            <i className={"fas " + (isExpanded ? "fa-compress-alt" : "fa-expand-alt")} />
          </button>
        </div>
      </div>
      <div className="cw-card-body-wrap">
        <div className="cw-ohlc-bar" ref={ohlcRef}>Hover over chart</div>
        <div className="cw-chart-container" style={{ height: isExpanded ? window.innerHeight - 130 : chartHeight }}>
          {error ? (
            <div className="cw-error-box"><i className="fas fa-exclamation-triangle" /> {error}</div>
          ) : !loaded ? (
            <div className="cw-loading-box"><div className="cw-spinner" /><span>Loading…</span></div>
          ) : null}
          <div ref={mountRef} style={{ width: "100%", height: "100%", position: error || !loaded ? "absolute" : "static", top: 0, visibility: error ? "hidden" : "visible" }} />
        </div>
        <div className="cw-legend">
          {LEGEND_ITEMS.map((item) => (
            <div key={item.period} className="cw-leg-item" style={{ cursor: "pointer", opacity: legendState[item.period] ? 1 : 0.35 }} title={`Toggle ${item.label}`} onClick={() => toggleLegend(item.period)}>
              <div className="cw-leg-dot" style={{ background: EMA_COLORS[item.period] }} />
              <span>{item.label}</span>
            </div>
          ))}
          <div className="cw-leg-item" style={{ cursor: "pointer", opacity: legendState.volume ? 1 : 0.35 }} title="Toggle volume" onClick={() => toggleLegend("volume")}>
            <div className="cw-leg-dot" style={{ background: "rgba(120,120,120,.6)" }} />
            <span>Volume</span>
          </div>
        </div>
      </div>
    </div>
  );
}
