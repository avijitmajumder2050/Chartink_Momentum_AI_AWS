"""AI-powered top-5 stock screener for the admin's scanner-campaign page —
takes the EMA 10/20 Breakout scanner's matched candidates, computes each
one's EMA(20/50/100/200) stack and recent volume vs its own average in
Python (deterministic, exact — an LLM doing bulk arithmetic over many
stocks' price series is exactly the kind of task it's unreliable at), then
asks Claude to judge the qualitative pattern: consolidation-then-breakout
on real volume, bullish EMA stack, no choppy wick action — the same shape
of setup TDPOWERSYS showed before its own breakout — and rank the best 5.

Self-contained (own API-key resolution), same pattern as
connectors/campaign_ai.py and connectors/ai_verdict.py.
"""

import os

import pandas as pd

try:
    import anthropic
    from pydantic import BaseModel
    from typing import List
except ImportError:
    anthropic = None
    BaseModel = object
    List = list

if anthropic is not None:
    class TopPick(BaseModel):
        symbol: str
        rank: int
        reason: str

    class ScreenResult(BaseModel):
        picks: List[TopPick]
else:
    TopPick = None
    ScreenResult = None

from connectors import secrets

MODEL = "claude-opus-5"

DEFAULT_SSM_PARAM = "/chartink-momentum-ai/anthropic_api_key"

# EMA200 needs a genuine 200-day window to mean anything — a candidate
# with less history than this is skipped rather than screened on a
# half-warmed-up average.
MIN_CANDLES_FOR_EMA200 = 200

# How many recent daily candles feed the choppiness check and Claude's
# view of near-term price action. 200 days of raw candles across up to 50
# stocks would be a huge, mostly-irrelevant payload — the EMA stack
# (computed from the full 200+ day history) already carries the long-term
# signal, this window is just for near-term shape.
RECENT_CANDLE_WINDOW = 20

# A candle counts as "wick-heavy" once its wicks (top + bottom combined)
# eat this fraction of the day's full high-low range — i.e. the real body
# is small relative to how far price got rejected in both directions.
WICK_HEAVY_RATIO = 0.6

# A candidate is "choppy" once at least this fraction of its recent
# candles are wick-heavy — price repeatedly getting rejected both ways
# rather than genuinely consolidating.
CHOPPY_CANDLE_FRACTION = 0.5

# claude-opus-5 has deprecated `temperature` entirely (a 400 error, not
# just ignored) — there is no API-level lever left to reduce sampling
# variance for this model. The actual fix is architectural: decide
# bullish-EMA-stack and choppiness deterministically in Python (see
# _is_choppy below) and pre-filter BEFORE the Claude call, so Claude's
# only job is ranking an already-qualified, deterministic candidate set —
# a much narrower task than "decide who even qualifies AND rank them",
# which is where most of the run-to-run variance was actually coming from.
SYSTEM_PROMPT = (
    "You rank Indian NSE equities that have ALREADY been confirmed (by "
    "deterministic code, not you) to have a bullish moving-average stack "
    "(EMA20 > EMA50 > EMA100 > EMA200) and non-choppy recent price "
    "action. Your only job is ranking them by how well each matches this "
    "specific setup: a quiet, tight consolidation followed by a breakout "
    "on above-average volume — the kind of setup a stock like TDPOWERSYS "
    "showed before its own breakout, an expansion candle on real volume, "
    "not just a small wiggle.\n\n"
    "For each candidate you're given: its symbol, its EMA values, "
    "today's volume as a ratio of its own 20-day average volume "
    "(already computed), its latest close/high/low, and its last 20 "
    "daily candles (date/open/high/low/close/volume).\n\n"
    "Rank strictly by consolidation tightness, breakout strength, and "
    "volume confirmation — if you spot something the automated "
    "pre-filter missed (e.g. still genuinely choppy despite passing the "
    "wick-ratio check, or a breakout that's actually just noise), you "
    "may exclude that one candidate rather than rank it, but this should "
    "be rare since the hard filtering already happened before you saw "
    "this list.\n\n"
    "Return the top 5 (or fewer if fewer candidates were given, or you "
    "excluded one — never pad the list) ranked 1 (best) downward, each "
    "with a short (1-2 sentence) concrete reason referencing what you "
    "actually saw, e.g. 'tight 8-day range before today's breakout on "
    "2.4x average volume, clean candles with small wicks'."
)


def _get_api_key():
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    param_name = os.environ.get("ANTHROPIC_API_KEY_SSM_PARAM", DEFAULT_SSM_PARAM)
    return secrets.get_parameter(param_name)


def _ema_last(closes, period):
    return float(pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1])


def _wick_ratio(candle):
    """(top wick + bottom wick) / full range for one candle — near 1.0
    means almost the whole range was wick (a tiny real body, price
    rejected hard both ways); near 0 means the body filled most of the
    range (a clean, decisive candle)."""
    day_range = candle["h"] - candle["l"]
    if day_range <= 0:
        return 0.0
    body_top = max(candle["o"], candle["c"])
    body_bottom = min(candle["o"], candle["c"])
    return ((candle["h"] - body_top) + (body_bottom - candle["l"])) / day_range


def _is_choppy(recent_candles):
    if not recent_candles:
        return False
    wick_heavy = sum(1 for c in recent_candles if _wick_ratio(c) >= WICK_HEAVY_RATIO)
    return (wick_heavy / len(recent_candles)) >= CHOPPY_CANDLE_FRACTION


def compute_candidate_metrics(symbol, bars):
    """bars: list of {time, open, high, low, close, volume} dicts, sorted
    ascending by date — exactly what connectors/chart_connector.get_ohlcv()
    returns. Returns None if there isn't enough history for a meaningful
    EMA200 (the caller should just skip this candidate, not fail the
    whole screen over one thin-history stock)."""
    if not bars or len(bars) < MIN_CANDLES_FOR_EMA200:
        return None

    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]

    ema20 = _ema_last(closes, 20)
    ema50 = _ema_last(closes, 50)
    ema100 = _ema_last(closes, 100)
    ema200 = _ema_last(closes, 200)

    # Trailing 20-day average volume EXCLUDING today, so "today vs its own
    # recent average" isn't comparing today against itself.
    prior_volumes = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    avg_volume_20 = (sum(prior_volumes) / len(prior_volumes)) if prior_volumes else None
    volume_ratio = (volumes[-1] / avg_volume_20) if avg_volume_20 else None

    recent = bars[-RECENT_CANDLE_WINDOW:]
    recent_candles = [
        {"date": b["time"], "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"], "v": b["volume"]}
        for b in recent
    ]

    return {
        "symbol": symbol,
        "bullish_stack": ema20 > ema50 > ema100 > ema200,
        "choppy": _is_choppy(recent_candles),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema100": round(ema100, 2),
        "ema200": round(ema200, 2),
        "latest_close": bars[-1]["close"],
        "latest_high": bars[-1]["high"],
        "latest_low": bars[-1]["low"],
        "volume_ratio_vs_20d_avg": round(volume_ratio, 2) if volume_ratio else None,
        "recent_candles": recent_candles,
    }


def _build_prompt(candidates):
    # Every candidate here already passed the bullish-EMA-stack and
    # choppiness pre-filter (see screen_top_picks) — not repeated per
    # candidate since it's now always true by construction; only the raw
    # EMA values (useful context for how strongly stacked) are included.
    lines = [f"{len(candidates)} pre-qualified candidates to rank (bullish EMA stack, non-choppy already confirmed):"]
    for c in candidates:
        lines.append(
            f"\n{c['symbol']}: EMA20={c['ema20']}, EMA50={c['ema50']}, EMA100={c['ema100']}, EMA200={c['ema200']}, "
            f"latest_close={c['latest_close']}, volume_vs_20d_avg={c['volume_ratio_vs_20d_avg']}x"
        )
        lines.append("Last 20 candles (date: O, H, L, C, V):")
        for candle in c["recent_candles"]:
            lines.append(f"  {candle['date']}: O={candle['o']} H={candle['h']} L={candle['l']} C={candle['c']} V={int(candle['v'])}")
    return "\n".join(lines)


def screen_top_picks(candidates):
    """candidates: list of dicts from compute_candidate_metrics(). Returns
    a list of {symbol, rank, reason} dicts, best (rank 1) first — may be
    shorter than 5 if fewer genuinely qualify (including empty, if none
    pass the deterministic pre-filter below). Raises RuntimeError on any
    failure (no API key, package missing, empty/malformed response) —
    this is a deliberate admin-initiated action, same posture as
    campaign_ai.generate_campaign_copy, not a best-effort/degrade-quietly
    call.

    claude-opus-5 has deprecated `temperature` (a hard 400 error, not
    just ignored), so there's no API-level way to reduce sampling
    variance for this model. The fix here is architectural instead:
    bullish-EMA-stack and choppiness are hard-filtered by deterministic
    Python (_is_choppy, computed in compute_candidate_metrics) BEFORE
    Claude ever sees the list — its only job left is ranking an
    already-qualified set, which is a far narrower, more consistent task
    than "decide who even qualifies AND rank them"."""
    if anthropic is None:
        raise RuntimeError("the anthropic package is not installed")
    if not candidates:
        raise RuntimeError("no candidates with enough history to screen")

    qualified = [c for c in candidates if c["bullish_stack"] and not c["choppy"]]
    if not qualified:
        return []  # nothing passed the hard filter — a real, correct result, not a failure

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("no Anthropic API key available (env var or SSM parameter)")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(qualified)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=ScreenResult,
    )
    result = response.parsed_output
    if not result:
        raise RuntimeError("empty response from Claude")
    picks = sorted(result.picks, key=lambda p: p.rank)[:5]
    return [{"symbol": p.symbol, "rank": p.rank, "reason": p.reason} for p in picks]
