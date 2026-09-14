// Reusable stock-chart preview modal — candlesticks + EMA(10/20/50)
// overlay + volume histogram, via lightweight-charts. A standalone,
// page-agnostic copy of the preview logic templates/scanner.html's own
// static/js/scanner.js built first, so any other page can offer the same
// "click a symbol to preview its chart" UX without depending on
// scanner.js's scanner-specific state (selected scanner, results table,
// etc.) — kept separate rather than importing from scanner.js.
//
// Usage on a page: include the lightweight-charts CDN script, then this
// file, and add the same #chartPreviewBackdrop/#chartPreviewClose/
// #chartPreviewSymbol/#chartPreviewFullLink/#chartPreviewBody modal
// markup as templates/scanner.html has (see templates/admin_scanner_
// campaign.html for a second real example). Then call
// window.openChartPreview(symbol) from a click handler.
(function () {
  "use strict";

  var EMA_COLORS = { 10: "#2962ff", 20: "#F2A93B", 50: "#aa00ff", 200: "#E0473F" };

  var previewBackdrop = document.getElementById("chartPreviewBackdrop");
  if (!previewBackdrop) return; // this page doesn't have the modal markup — nothing to wire up

  var previewClose = document.getElementById("chartPreviewClose");
  var previewSymbolEl = document.getElementById("chartPreviewSymbol");
  var previewFullLink = document.getElementById("chartPreviewFullLink");
  var previewBody = document.getElementById("chartPreviewBody");
  var previewChart = null; // {chart, resizeObserver} of whatever's currently mounted
  var previewGen = 0; // guards a stale fetch from rendering into a closed/reopened modal

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function disposePreviewChart() {
    if (!previewChart) return;
    try { previewChart.resizeObserver.disconnect(); } catch (e) {}
    try { previewChart.chart.remove(); } catch (e) {}
    previewChart = null;
  }

  function closePreview() {
    previewGen++;
    previewBackdrop.setAttribute("hidden", "");
    disposePreviewChart();
    previewBody.innerHTML = '<div class="chart-preview-loading">Loading chart…</div>';
  }

  function openPreview(symbol) {
    var gen = ++previewGen;
    previewSymbolEl.textContent = symbol;
    previewFullLink.setAttribute("href", "/markets/chart?symbol=" + encodeURIComponent(symbol));
    previewBody.innerHTML = '<div class="chart-preview-loading">Loading chart…</div>';
    previewBackdrop.removeAttribute("hidden");

    fetch("/api/chart/data?symbol=" + encodeURIComponent(symbol))
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (gen !== previewGen) return; // modal closed/reopened for another symbol meanwhile

        if (!result.ok || !result.data.bars || !result.data.bars.length) {
          previewBody.innerHTML =
            '<div class="chart-preview-error">' +
            escapeHtml((result.data && result.data.error) || "No chart data for " + symbol) +
            "</div>";
          return;
        }

        renderPreviewChart(result.data.bars, gen);
      })
      .catch(function (err) {
        if (gen !== previewGen) return;
        previewBody.innerHTML = '<div class="chart-preview-error">' + escapeHtml(err.message || "Failed to load chart") + "</div>";
      });
  }

  function calcEMA(data, period) {
    if (!data || data.length === 0) return [];
    var multiplier = 2 / (period + 1);
    var ema = data[0].close;
    var result = [{ time: data[0].time, value: ema }];
    for (var i = 1; i < data.length; i++) {
      ema = (data[i].close - ema) * multiplier + ema;
      result.push({ time: data[i].time, value: Number(ema.toFixed(2)) });
    }
    return result;
  }

  function renderPreviewChart(bars, gen) {
    disposePreviewChart();
    if (gen !== previewGen) return; // guard against a race during disposal
    previewBody.innerHTML = "";

    var chart = LightweightCharts.createChart(previewBody, {
      width: previewBody.clientWidth,
      height: previewBody.clientHeight,
      layout: { background: { type: "solid", color: "#ffffff" }, textColor: "#333333", fontSize: 11 },
      grid: { vertLines: { color: "rgba(0,0,0,.04)" }, horzLines: { color: "rgba(0,0,0,.04)" } },
      rightPriceScale: { borderColor: "#ddd" },
      timeScale: { borderColor: "#ddd", rightOffset: 4, barSpacing: 7 },
    });

    var candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: "#17A673", downColor: "#E0473F", borderVisible: false, wickUpColor: "#17A673", wickDownColor: "#E0473F",
    });
    candleSeries.setData(bars);

    [10, 20, 50].forEach(function (period) {
      var series = chart.addSeries(LightweightCharts.LineSeries, {
        color: EMA_COLORS[period], lineWidth: period === 50 ? 1 : 2, priceLineVisible: false, lastValueVisible: true,
      });
      series.setData(calcEMA(bars, period));
    });

    var volSeries = chart.addSeries(LightweightCharts.HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volSeries.setData(
      bars.map(function (b) {
        return { time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(23,166,115,.45)" : "rgba(224,71,63,.45)" };
      })
    );

    chart.timeScale().fitContent();

    var resizeObserver = new ResizeObserver(function (entries) {
      if (!previewChart || previewChart.chart !== chart) return;
      var e = entries[0];
      if (e) chart.applyOptions({ width: e.contentRect.width, height: e.contentRect.height });
    });
    resizeObserver.observe(previewBody);

    previewChart = { chart: chart, resizeObserver: resizeObserver };
  }

  previewClose.addEventListener("click", closePreview);
  previewBackdrop.addEventListener("click", function (e) {
    if (e.target === previewBackdrop) closePreview();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !previewBackdrop.hasAttribute("hidden")) closePreview();
  });

  window.openChartPreview = openPreview;
})();
