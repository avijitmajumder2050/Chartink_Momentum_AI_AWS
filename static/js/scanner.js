(function () {
  "use strict";

  var EMA_COLORS = { 10: "#2962ff", 20: "#F2A93B", 50: "#aa00ff", 200: "#E0473F" };

  var previewBackdrop = document.getElementById("chartPreviewBackdrop");
  var previewClose = document.getElementById("chartPreviewClose");
  var previewSymbolEl = document.getElementById("chartPreviewSymbol");
  var previewFullLink = document.getElementById("chartPreviewFullLink");
  var previewBody = document.getElementById("chartPreviewBody");
  var previewChart = null; // {chart, resizeObserver} of whatever's currently mounted
  var previewGen = 0; // guards a stale fetch from rendering into a closed/reopened modal

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

  var listEl = document.getElementById("scannerList");
  var options = Array.prototype.slice.call(
    listEl.querySelectorAll(".scanner-option")
  );
  var runBtn = document.getElementById("runBtn");
  var statusEl = document.getElementById("status");
  var statsEl = document.getElementById("stats");
  var tableWrap = document.getElementById("tableWrap");
  var metaEl = document.getElementById("meta");
  var descEl = document.getElementById("scannerDesc");

  var selectedId = window.INITIAL_SCANNER_ID || "";

  function getSelectedOption() {
    return options.filter(function (o) {
      return o.getAttribute("data-id") === selectedId;
    })[0];
  }

  function describeScanner() {
    var opt = getSelectedOption();
    descEl.textContent = opt ? opt.getAttribute("data-description") || "" : "";
  }

  function selectScanner(id) {
    selectedId = id;
    options.forEach(function (o) {
      o.classList.toggle("selected", o.getAttribute("data-id") === id);
    });
    describeScanner();
    setStatus("", "");
    statsEl.innerHTML = "";
    tableWrap.innerHTML = "";
    metaEl.textContent = "";
    loadCachedResult(id);
  }

  function loadCachedResult(id) {
    // Shows the last cached run, if any — read-only, never triggers a
    // live scan (selecting a scanner should not "run" it).
    fetch("/api/scanners/" + encodeURIComponent(id) + "/cached")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (id !== selectedId || !data.cached) return;
        renderStats(data.stats);
        renderTable(data.columns, data.rows);
        metaEl.textContent = "Cached result from " + data.generated_at + " — click Run Scan to refresh";
      })
      .catch(function () { /* no cached result available — leave blank */ });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderStats(stats) {
    statsEl.innerHTML = (stats || [])
      .map(function (s) {
        return (
          '<div class="stat">' +
          '<div class="value">' + escapeHtml(s.value) + "</div>" +
          '<div class="label">' + escapeHtml(s.label) + "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  function isNumericType(type) {
    return type === "num" || type === "pct";
  }

  function formatCell(col, row) {
    var value = row[col.key];

    if (value === null || value === undefined || value === "") {
      return '<span class="dim">-</span>';
    }

    if (col.type === "bool") {
      return value
        ? '<span class="badge">YES</span>'
        : '<span class="dim">No</span>';
    }

    if (col.type === "symbol") {
      var symbol = String(value).trim();
      return (
        '<a class="symbol-link" href="/markets/chart?symbol=' +
        encodeURIComponent(symbol) +
        '" target="_blank" rel="noopener">' +
        escapeHtml(symbol) +
        "</a>"
      );
    }

    if (col.type === "pct") {
      var num = Number(value);
      if (!Number.isFinite(num)) return escapeHtml(value);
      var cls = num >= 0 ? "up" : "down";
      var sign = num >= 0 ? "+" : "";
      return '<span class="' + cls + '">' + sign + num.toFixed(2) + "%</span>";
    }

    if (col.type === "num") {
      var n = Number(value);
      return Number.isFinite(n) ? '<span class="num">' + n.toLocaleString("en-IN") + "</span>" : escapeHtml(value);
    }

    return escapeHtml(value);
  }

  function renderTable(columns, rows) {
    if (!rows || !rows.length) {
      tableWrap.innerHTML = '<div class="empty">No matches</div>';
      return;
    }

    var thead = columns
      .map(function (c) {
        return (
          '<th class="' + (isNumericType(c.type) ? "num" : "") + '">' +
          escapeHtml(c.label) +
          "</th>"
        );
      })
      .join("");

    var tbody = rows
      .map(function (row) {
        var cells = columns
          .map(function (c) {
            return (
              '<td class="' + (isNumericType(c.type) ? "num" : "") + '">' +
              formatCell(c, row) +
              "</td>"
            );
          })
          .join("");
        return "<tr>" + cells + "</tr>";
      })
      .join("");

    tableWrap.innerHTML =
      '<div class="table-wrap"><table><thead><tr>' +
      thead +
      "</tr></thead><tbody>" +
      tbody +
      "</tbody></table></div>";
  }

  function setStatus(text, mode) {
    statusEl.textContent = text || "";
    statusEl.className = "status" + (mode ? " " + mode : "");
  }

  function runScanner() {
    var id = selectedId;

    if (!id) {
      setStatus("", "");
      statsEl.innerHTML = "";
      tableWrap.innerHTML = "";
      metaEl.textContent = "";
      return;
    }

    runBtn.disabled = true;
    setStatus(
      "Running scanner on the backend — this can take a few seconds…",
      "loading"
    );
    statsEl.innerHTML = "";
    tableWrap.innerHTML = "";
    metaEl.textContent = "";

    fetch("/api/scanners/" + encodeURIComponent(id) + "/run")
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        var data = result.data;

        if (!result.ok || data.error) {
          setStatus("Error: " + (data.error || "Unknown error"), "error");
          return;
        }

        setStatus("", "");
        renderStats(data.stats);
        renderTable(data.columns, data.rows);
        metaEl.textContent = "Generated " + data.generated_at;
      })
      .catch(function (err) {
        setStatus("Request failed: " + err.message, "error");
      })
      .finally(function () {
        runBtn.disabled = false;
      });
  }

  tableWrap.addEventListener("click", function (e) {
    var link = e.target.closest(".symbol-link");
    if (!link) return;
    e.preventDefault();
    openPreview(link.textContent);
  });

  options.forEach(function (opt) {
    opt.addEventListener("click", function () {
      selectScanner(opt.getAttribute("data-id"));
    });
  });

  runBtn.addEventListener("click", runScanner);

  describeScanner();
})();
