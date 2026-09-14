# AI Summary — how it works

The "AI Summary" card on the Stock Research page (`/markets/research?symbol=...`)
is a short, Claude-generated read of a stock's fundamentals. This document
explains exactly what data feeds it, how the model is instructed, and what
it deliberately does **not** do.

Source: `connectors/ai_verdict.py`, called from `app.py`'s `research()` route
after the other data sources (screener.in, MarketSmith India) have already
been fetched for the page.

## This is not a scoring formula

There is no hardcoded rule like `if debt_to_equity > 1: label = "Weak"`.
The KPIs below are handed to Claude (`claude-opus-5`) as plain text, and the
model itself judges what "Strong" / "Mixed" / "Weak" means by weighing them
together — the same way a human analyst would read a ratios table, not a
fixed threshold check. That means:

- The same numbers could plausibly get a different label than you'd
  expect if you mentally apply your own thresholds — it's a qualitative
  read, not arithmetic.
- Re-running it on the same data isn't guaranteed to produce byte-identical
  wording, though it's cached for 24h per symbol precisely so it doesn't
  regenerate (and potentially vary) on every page load.
- It only knows what's listed below. It has no memory of the stock's
  history, sector, competitors, or news beyond what's in this list.

## KPIs it receives

Built by `_build_prompt()` in `connectors/ai_verdict.py`. For a given
symbol, the model sees a plain-text list like:

```
Stock: Tata Consultancy Services Ltd (TCS)
Price: ₹4,102.15, change 0.38% (down)
Market Cap: ₹14.8 L Cr
Current Price: ₹4,102.15
High / Low: ₹4,592 / ₹2,955
Stock P/E: 28.4
Book Value: ₹...
Dividend Yield: 2.91%
ROCE: 63%
ROE: 46-52%
Face Value: ₹1
ROCE %: 63.0
OPM %: 27.0
Debt / Equity: 0.09
ROE %: 46.0
EPS Strength (1-99 percentile): 78
Price Strength (1-99 percentile): 27
```

| Block | Fields | Source |
|---|---|---|
| Header | Name, current price, day change | `fundamentals_connector.get_research_data()` → `header` (scraped from screener.in's page header) |
| Key ratios | Market Cap, Current Price, High/Low, Stock P/E, Book Value, Dividend Yield, ROCE, ROE, Face Value | same call → `fundamentals` (screener.in's `#top-ratios` block — exact fields screener.in publishes for that company, so this list can vary slightly by stock) |
| 5-year ratio trend | ROCE %, OPM %, Debt / Equity, ROE % (up to 4) | `fundamentals_connector.get_fundamentals_data()` → `ratios` (computed by this app from screener.in's P&L/balance-sheet tables — see `add_ratio()` in `connectors/fundamentals_connector.py`) |
| Momentum ratings | EPS Strength, Price Strength (1–99 percentile each) | `marketsmith_connector.get_strength_ratings()` (rendered from marketsmithindia.com's guest-visible evaluation page) |

Any field that failed to scrape for a given stock is simply absent from the
list — the model is never told "N/A" is a real weakness, it just doesn't
see that line at all.

## What the model is asked to do

Full system prompt, verbatim (`SYSTEM_PROMPT` in `connectors/ai_verdict.py`):

> You assess a stock's current fundamentals for a retail investor research
> page, using only the metrics given to you. Classify the overall
> fundamental picture as 'Strong', 'Mixed', or 'Weak', based on valuation,
> profitability, leverage and momentum. Write a two-to-three sentence
> factual summary of what the numbers show, in plain language a beginner
> understands. Separately list every specific weakness you notice (e.g.
> high debt, thin margins, weak momentum, rich valuation) as short phrases
> — an empty list only if there are genuinely none. If the summary
> mentions anything negative or soft about the stock, that same point must
> also appear in the weaknesses list — the two must never disagree. Never
> tell the reader to buy, sell, or hold, and never give a price target —
> assess and describe the fundamentals, don't recommend the stock. No
> preamble, no disclaimers, no markdown, plain sentences only in the
> summary.

The response is constrained to a JSON schema (via the API's structured
outputs / `client.messages.parse()`) so the reply always has exactly:

| Field | Type | Rendered as |
|---|---|---|
| `label` | `"Strong"` \| `"Mixed"` \| `"Weak"` | Color badge next to "AI Summary" (green / amber / red) — `templates/research.html` |
| `summary` | free text, 2–3 sentences | The paragraph under the badge |
| `weaknesses` | list of short strings (can be empty) | "Weak points" bullet list — hidden entirely when empty |

## Model & cost

- Model: `claude-opus-5`, `output_config.effort: "low"` (kept low since this
  is a short, bounded summarization task, not open-ended reasoning).
- `max_tokens`: 400.
- Cached 24 hours per symbol (`connectors/cache.py`, key `ai_verdict_<SYMBOL>`)
  — fundamentals don't move intraday, and this is a real billed API call,
  so it isn't regenerated on every page view.
- Best-effort: if `anthropic` isn't installed, no API key is available
  (see below), or the call fails for any reason, `app.py` logs the
  exception and the page renders normally with the AI Summary card simply
  absent — it never blocks the rest of the Research page.

## API key

Resolved by `_get_api_key()` in `connectors/ai_verdict.py`, in order:

1. `ANTHROPIC_API_KEY` environment variable (local dev convenience).
2. AWS SSM Parameter Store, `SecureString` at
   `/chartink-momentum-ai/anthropic_api_key` (override the path with the
   `ANTHROPIC_API_KEY_SSM_PARAM` env var). Fetched via `connectors/secrets.py`
   using boto3's default credential chain — set `AWS_PROFILE` to choose
   which AWS account/profile it reads from. Never written to disk; cached
   in memory only for 15 minutes.

## Compliance posture

- Labeled "AI Summary" on the page with the caption "AI-generated from the
  fundamentals on this page — not investment advice", consistent with the
  site-wide disclaimer in `templates/_footer.html` ("Quantile is a research
  and analytics platform, not a SEBI-registered investment adviser...").
- The prompt explicitly forbids buy/sell/hold language and price targets —
  it only describes and classifies the fundamentals themselves.
- "Strong" / "Mixed" / "Weak" describes the financial data, not a trading
  signal — it is not equivalent to a broker's "Buy" / "Hold" / "Sell"
  rating.

## Known limitations

- No numeric scoring/weighting is exposed — you can't ask "why 62% weight
  on ROE" because there isn't one; it's a single LLM judgment call, by
  design, over a fixed set of inputs.
- Doesn't account for anything outside the listed KPIs: no sector
  comparison, no macro context, no recent news, no long-term price chart.
- Screener.in's ratio labels vary slightly by company type (e.g. banks
  report "Borrowing" instead of "Borrowings" — see the comment in
  `connectors/fundamentals_connector.py`), so the exact KPI list in the
  "Key ratios" block can differ stock to stock.
- LLM output for the same inputs can vary in wording (not in the
  underlying facts) between the 24h cache windows.
