import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts";
import { apiFetch } from "../api/client";

// Ported from templates/chart.html. GET /api/chart/bootstrap (new — see
// the rewrite plan) replaces the symbol-list + default-symbol-resolution
// logic that used to be inline in chart_page(); GET /api/chart/data
// (already existed) still serves the bars for whichever symbol is chosen.

const EMA_COLORS = { 10: "#2962ff", 20: "#F2A93B", 50: "#aa00ff", 200: "#E0473F" };

function calcEMA(data, period) {
  if (!data.length) return [];
  const multiplier = 2 / (period + 1);
  let ema = data[0].close;
  const result = [{ time: data[0].time, value: ema }];
  for (let i = 1; i < data.length; i++) {
    ema = (data[i].close - ema) * multiplier + ema;
    result.push({ time: data[i].time, value: Number(ema.toFixed(2)) });
  }
  return result;
}

export default function Chart() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSymbol = searchParams.get("symbol") || "";

  const [bootstrap, setBootstrap] = useState(null); // {symbols, indices, defaultSymbol}
  const [symbol, setSymbol] = useState(urlSymbol || null);
  const [bars, setBars] = useState(null); // null = not loaded yet
  const [notFound, setNotFound] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [searchInput, setSearchInput] = useState(urlSymbol);

  const containerRef = useRef(null);
  const chartRef = useRef(null);

  // Bootstrap: symbol list + indices + resolve which symbol to show first.
  useEffect(() => {
    const qs = urlSymbol ? `?symbol=${encodeURIComponent(urlSymbol)}` : "";
    apiFetch(`/api/chart/bootstrap${qs}`)
      .then((res) => res.json())
      .then((data) => {
        setBootstrap(data);
        if (!symbol) setSymbol(data.defaultSymbol || null);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolve default symbol once on mount, same as the old server-rendered bootstrap
  }, []);

  // Whenever the resolved symbol changes, fetch its bars.
  useEffect(() => {
    if (!symbol) return;
    setBars(null);
    setNotFound(false);
    setUnavailable(false);

    apiFetch(`/api/chart/data?symbol=${encodeURIComponent(symbol)}`)
      .then((res) => res.json().then((data) => ({ status: res.status, data })))
      .then(({ status, data }) => {
        if (status === 404) {
          setNotFound(true);
          return;
        }
        if (status !== 200) {
          setUnavailable(true);
          return;
        }
        setBars(data.bars || []);
      })
      .catch(() => setUnavailable(true));
  }, [symbol]);

  // Chart rendering — separate effect so switching symbols disposes and
  // recreates cleanly, same lifecycle as ChartPreviewModal.
  useEffect(() => {
    if (!bars || !bars.length || !containerRef.current) return;
    const container = containerRef.current;

    const chart = createChart(container, {
      height: 520,
      layout: { background: { type: "solid", color: "#FFFFFF" }, textColor: "#5B6270", fontSize: 11 },
      grid: { vertLines: { color: "rgba(20,23,31,0.04)" }, horzLines: { color: "rgba(20,23,31,0.04)" } },
      crosshair: { mode: 1 }, // CrosshairMode.Normal
      rightPriceScale: { borderColor: "#E3E6EC" },
      timeScale: { borderColor: "#E3E6EC", rightOffset: 6, barSpacing: 7 },
      handleScroll: true,
      handleScale: true,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#17A673", downColor: "#E0473F", borderVisible: false, wickUpColor: "#17A673", wickDownColor: "#E0473F",
    });
    candleSeries.setData(bars);

    [10, 20, 50, 200].forEach((period) => {
      const series = chart.addSeries(LineSeries, {
        color: EMA_COLORS[period], lineWidth: period <= 20 ? 2 : 1, priceLineVisible: false, lastValueVisible: true,
      });
      series.setData(calcEMA(bars, period));
    });

    const volSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volSeries.setData(bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(23,166,115,.45)" : "rgba(224,71,63,.45)" })));

    chart.timeScale().fitContent();

    function onResize() {
      chart.applyOptions({ width: container.clientWidth });
    }
    window.addEventListener("resize", onResize);

    chartRef.current = chart;
    return () => {
      window.removeEventListener("resize", onResize);
      try { chart.remove(); } catch { /* already gone */ }
      chartRef.current = null;
    };
  }, [bars]);

  function navigateToSymbol(sym) {
    setSearchParams(sym ? { symbol: sym } : {});
    setSymbol(sym);
    setSearchInput(sym);
  }

  function onSearchSubmit(e) {
    e.preventDefault();
    if (searchInput.trim()) navigateToSymbol(searchInput.trim().toUpperCase());
  }

  const symbols = bootstrap?.symbols || [];
  const indices = bootstrap?.indices || [];

  if (bootstrap && !symbol) {
    return (
      <div style={{ width: "100%", padding: "64px 48px" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
          <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Chart data temporarily unavailable</h2>
          <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach the chart data source just now. Please try again shortly.</p>
        </div>
      </div>
    );
  }

  const last = bars && bars.length ? bars[bars.length - 1] : null;
  const prev = bars && bars.length > 1 ? bars[bars.length - 2] : last;
  const chg = last && prev && prev.close ? ((last.close - prev.close) / prev.close) * 100 : 0;
  const up = chg >= 0;

  return (
    <>
      <div style={{ width: "100%", padding: "20px 24px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 10 }}>
          <form
            onSubmit={onSearchSubmit}
            style={{ display: "flex", alignItems: "center", gap: 8, background: "#FFFFFF", border: "1.5px solid #E3E6EC", borderRadius: 10, padding: "10px 14px" }}
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="#8A90A0" strokeWidth="1.5">
              <circle cx="6.5" cy="6.5" r="5" />
              <path d="M10.5 10.5L14 14" />
            </svg>
            <input
              list="chartSymbolOptions"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="search-input"
              placeholder="Any NSE symbol or index — try TCS, NIFTY 50, or pick from the watchlist"
              autoComplete="off"
            />
            <datalist id="chartSymbolOptions">
              {indices.map((i) => <option key={i} value={i} />)}
              {symbols.map((s) => <option key={s.symbol} value={s.symbol} />)}
            </datalist>
          </form>
          {indices.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {indices.map((i) => (
                <button
                  type="button"
                  key={i}
                  className={"pill-tab" + (symbol === i.replace(/ /g, "") ? " active" : "")}
                  onClick={() => navigateToSymbol(i)}
                  style={{ border: "none", cursor: "pointer" }}
                >
                  {i}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {unavailable ? (
        <div style={{ width: "100%", padding: "64px 48px" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Chart data temporarily unavailable</h2>
            <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach the chart data source just now. Please try again shortly.</p>
          </div>
        </div>
      ) : notFound ? (
        <div style={{ width: "100%", padding: "64px 48px" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>No chart data for "{symbol}"</h2>
            <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>
              We couldn't find that symbol in the watchlist or on NSE. Try the exact exchange symbol, e.g. <strong>TCS</strong>, <strong>INFY</strong>, <strong>RELIANCE</strong>.
            </p>
          </div>
        </div>
      ) : (
        <div style={{ width: "100%", padding: "12px 24px 20px", display: "flex", gap: 18, alignItems: "flex-start" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: "14px 18px" }}>
              <span style={{ fontSize: 15, fontWeight: 700, display: "block", lineHeight: 1.1 }}>{symbol}</span>
              <span className="num" style={{ fontSize: 12, color: "#8A90A0", fontWeight: 600 }}>
                {last ? (
                  <>
                    ₹{last.close.toLocaleString("en-IN")}{" "}
                    <span style={{ color: up ? "#17A673" : "#E0473F" }}>
                      {up ? "+" : ""}
                      {chg.toFixed(2)}%
                    </span>{" "}
                    <span style={{ color: "#B0B4C0" }}>({last.time})</span>
                  </>
                ) : (
                  "—"
                )}
              </span>
            </div>

            <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
              {bars && !bars.length ? (
                <div style={{ height: 520, display: "flex", alignItems: "center", justifyContent: "center", color: "#8A90A0", fontSize: 13.5 }}>
                  No chart data for this symbol.
                </div>
              ) : (
                <div ref={containerRef} style={{ width: "100%", height: 520 }} />
              )}
              <p style={{ fontSize: 11, color: "#B0B4C0", margin: "10px 0 0" }}>
                Daily OHLCV — momentum watchlist data store, with a Dhan security-master + historical-data fallback for symbols outside it. EMA 10/20/50/200 overlays.
              </p>
            </div>
          </div>

          <div style={{ width: 280, flexShrink: 0, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 4, maxHeight: 640, overflowY: "auto" }}>
            <span style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>Momentum watchlist</span>
            <span style={{ fontSize: 11, color: "#8A90A0", marginBottom: 10 }}>Sorted by RS Rating</span>
            {symbols.map((s) => (
              <button
                type="button"
                key={s.symbol}
                onClick={() => navigateToSymbol(s.symbol)}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 8px", borderRadius: 8,
                  background: s.symbol === symbol ? "#EEEDFD" : "transparent", border: "none", cursor: "pointer", textAlign: "left",
                }}
              >
                <span style={{ fontSize: 13, fontWeight: 700, color: s.symbol === symbol ? "#4640DE" : "#14171F" }}>{s.symbol}</span>
                <span className="num" style={{ fontSize: 12, fontWeight: 600, color: "#8A90A0" }}>RS {s.rsRating}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
