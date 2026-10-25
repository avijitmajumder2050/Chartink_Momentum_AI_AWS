# Results Scanner

Quarterly-results screens on their own page, **Markets › Results Scanner**
(`/markets/results-scanner`, `frontend/src/pages/ResultsScanner.jsx`):
quarter picker, preset chips, a nested AND/OR condition builder, exclude
negative base / exclude financials / min market cap, sortable table with
All / Clean / Financials / Needs review tabs, CSV export, criteria in the
URL (`?q=`) so a scan can be shared, and a "relax" offer when nothing
matches.

| Preset | Conditions |
|---|---|
| QoQ Momentum | Sales QoQ > 2.6, Profit QoQ > 8, EBITDA QoQ > 8, OPM QoQ > 3, EPS QoQ > 6 |
| QoQ 10/10 | Sales QoQ > 10, Profit QoQ > 10 |
| QoQ + YoY strong | QoQ Momentum + Profit YoY > 0 |

Presets are free for any signed-in user; custom criteria need Pro/Premium,
enforced by `POST /api/results-scanner` (`code: "PRO_REQUIRED"`).
`GET /api/results-scanner/meta` serves fields, operators, presets and the
quarters available.

Code: `connectors/results_scanner.py` (fetching, store, metrics, criteria,
presets) and the two `/api/results-scanner` endpoints in `app.py`.
Tests: `tests/test_results_scanner.py` on saved pages in
`tests/fixtures/results_scanner/` — no live calls.

## Data

- **Stock list:** `s3://new-dhan-trading-data/marketsmith-data/input/raw_mapping_all_symbols.csv`
  (`Stock Name`, `Market Cap`), read at every refresh.
- **Numbers:** each company's public screener.in page, consolidated first,
  standalone if the consolidated table is empty. Quarterly Sales (banks:
  Revenue), Operating Profit (= EBITDA; banks: Financing Profit), Net Profit,
  EPS. OPM is recomputed unrounded as Operating Profit / Sales.
- **Why not Trendlyne Rapid Results or screener query screens:** Trendlyne's
  robots.txt disallows `*/rapid-results/all/` for all bots, and screener.in's
  disallows `?page=` on query screens. Both would need permission or an API.
- Screener's Operating Profit isn't identical to Trendlyne's EBITDA, so some
  QoQ figures differ between the two (e.g. HCL Tech Sep '26: 8.3% here vs
  6.6% on Trendlyne).

## Refresh

A daemon thread (`results_scanner.start_refresher`, started from `wsgi.py`)
runs one pass each weekday between 09:05 and 10:55 IST — the backend only
runs 09:00–11:00 — and resumes the next day if it doesn't finish.

- One request every 2 s, retries with backoff (longer after HTTP 429),
  robots.txt checked before every fetch, User-Agent
  `QuantileResultsScanner/1.0`.
- A company already showing the target quarter (latest ended calendar
  quarter) is re-checked only weekly; one that hasn't reported, daily. So
  the first pass over ~1,140 stocks takes ~40–75 min, later ones far less.
- Store: `.cache/results_scanner_store.json` on the backend instance.
  "First seen" is the date the refresher first saw a quarter — for the first
  pass that's the pass date, not the announcement date.

## Metrics and flags

- QoQ %: sales, EBITDA, OPM (relative: `(OPM_now / OPM_prev − 1) × 100`),
  net profit, EPS. YoY %: sales, EBITDA, net profit, EPS. Absolute: sales,
  net profit, market cap.
- A % whose base is ≤ 0 is null and fails every numeric condition.
- Flags: `financial` (bank / NBFC / insurer / AMC from name or screener
  industry), `small_base` (previous-quarter profit < 5% of current),
  `yoy_decline` (profit YoY < 0), `extreme_move` (any QoQ % > 300).
- Criteria are nested AND/OR groups:
  `{"op": "AND", "rules": [{"field": "sales_qoq", "operator": ">", "value": 10}, {"op": "OR", "rules": [...]}]}`;
  operators `> >= < <= between` (`between` takes `[low, high]`). With zero
  matches the scanner shows which single condition removed the most companies.

## Settings (env vars, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `RESULTS_SCANNER_REQUEST_INTERVAL` | `2` | Seconds between requests to screener.in |
| `RESULTS_SCANNER_CACHE_TTL` | `900` | Seconds a scan result is cached (key: source, quarter, criteria hash) |

No login or cookie is needed — only public company pages are read.

## Adding a data source (e.g. NSE/BSE XBRL)

1. Write a class with `fetch(symbol) -> {"quarters": {"2026-09": {"sales",
   "ebitda", "opm", "net_profit", "eps"}}, "industry": [...], "name": str}`
   (or `None` if the company isn't found), using `RateLimiter` and its own
   robots/terms checks.
2. Register it in `results_scanner.SOURCES`.
3. Pass it to `refresh_store(source=...)` (or give it its own store path) —
   metrics, flags, criteria and the page work unchanged.
4. Add saved-response fixtures and tests under `tests/`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests -q
```
