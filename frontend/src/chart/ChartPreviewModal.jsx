import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts";
import { apiFetch } from "../api/client";

const EMA_COLORS = { 10: "#2962ff", 20: "#F2A93B", 50: "#aa00ff" };

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

export default function ChartPreviewModal({ symbol, onClose }) {
  // mountRef points to a div lightweight-charts owns completely (it
  // injects its own canvas directly into it) — kept separate from
  // anything React re-renders into, so the two never fight over the same
  // DOM node's children.
  const mountRef = useRef(null);
  const chartRef = useRef(null); // {chart, resizeObserver} of whatever's currently mounted
  const [state, setState] = useState({ loading: true, error: null });

  function disposeChart() {
    if (!chartRef.current) return;
    try { chartRef.current.resizeObserver.disconnect(); } catch { /* already gone */ }
    try { chartRef.current.chart.remove(); } catch { /* already gone */ }
    chartRef.current = null;
  }

  function renderChart(bars) {
    disposeChart();
    const mount = mountRef.current;
    if (!mount) return;

    const chart = createChart(mount, {
      width: mount.clientWidth,
      height: mount.clientHeight,
      layout: { background: { type: "solid", color: "#ffffff" }, textColor: "#333333", fontSize: 11 },
      grid: { vertLines: { color: "rgba(0,0,0,.04)" }, horzLines: { color: "rgba(0,0,0,.04)" } },
      rightPriceScale: { borderColor: "#ddd" },
      timeScale: { borderColor: "#ddd", rightOffset: 4, barSpacing: 7 },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#17A673", downColor: "#E0473F", borderVisible: false, wickUpColor: "#17A673", wickDownColor: "#E0473F",
    });
    candleSeries.setData(bars);

    [10, 20, 50].forEach((period) => {
      const series = chart.addSeries(LineSeries, {
        color: EMA_COLORS[period], lineWidth: period === 50 ? 1 : 2, priceLineVisible: false, lastValueVisible: true,
      });
      series.setData(calcEMA(bars, period));
    });

    const volSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volSeries.setData(
      bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(23,166,115,.45)" : "rgba(224,71,63,.45)" }))
    );

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver((entries) => {
      if (!chartRef.current || chartRef.current.chart !== chart) return;
      const entry = entries[0];
      if (entry) chart.applyOptions({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    resizeObserver.observe(mount);

    chartRef.current = { chart, resizeObserver };
  }

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null });

    apiFetch(`/api/chart/data?symbol=${encodeURIComponent(symbol)}`)
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        if (cancelled) return;
        if (!result.ok || !result.data.bars || !result.data.bars.length) {
          setState({ loading: false, error: (result.data && result.data.error) || `No chart data for ${symbol}` });
          return;
        }
        setState({ loading: false, error: null });
        renderChart(result.data.bars);
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ loading: false, error: err.message || "Failed to load chart" });
      });

    return () => {
      cancelled = true;
      disposeChart();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- renderChart/disposeChart are stable per-mount, symbol is the only real dep
  }, [symbol]);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      style={{ background: "rgba(20,23,31,0.45)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="chart-preview-box">
        <button type="button" aria-label="Close" className="chart-preview-close" onClick={onClose}>
          &times;
        </button>
        <div className="chart-preview-head">
          <span className="chart-preview-symbol">{symbol}</span>
          <a href={`/markets/chart?symbol=${encodeURIComponent(symbol)}`} target="_blank" rel="noopener noreferrer" className="chart-preview-full-link">
            Open full chart ↗
          </a>
        </div>
        <div className="chart-preview-body">
          {state.loading && <div className="chart-preview-loading">Loading chart…</div>}
          {state.error && <div className="chart-preview-error">{state.error}</div>}
          <div ref={mountRef} style={{ width: "100%", height: "100%" }} />
        </div>
      </div>
    </div>
  );
}
