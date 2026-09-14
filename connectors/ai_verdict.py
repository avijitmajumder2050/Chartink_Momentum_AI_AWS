"""AI-generated stock verdict — a short, factual summary written by Claude
from the fundamentals/ratios/rating data already fetched for the Research
page. This is generated text, not investment advice — research.html labels
it as AI-generated, consistent with the site-wide disclaimer in
templates/_footer.html.

Best-effort, same as marketsmith_connector: if the `anthropic` package
isn't installed, no API key is available, or the API call fails, the
caller should just omit the verdict rather than fail the page.

API key resolution: ANTHROPIC_API_KEY env var first (local dev
convenience), else the ANTHROPIC_API_KEY_SSM_PARAM path in AWS SSM
Parameter Store (see connectors/secrets.py) — set AWS_PROFILE to pick
which AWS account/profile boto3 uses.
"""

import os

try:
    import anthropic
    from pydantic import BaseModel
    from typing import List, Literal

    class StockVerdict(BaseModel):
        label: Literal["Strong", "Mixed", "Weak"]
        summary: str
        weaknesses: List[str]
except ImportError:
    anthropic = None
    StockVerdict = None

from connectors import cache, secrets

MODEL = "claude-opus-5"

DEFAULT_SSM_PARAM = "/chartink-momentum-ai/anthropic_api_key"

# Fundamentals don't change intraday and this costs a real API call, so
# cache generously — same rationale as marketsmith_connector's 24h TTL.
CACHE_TTL_SECONDS = 24 * 60 * 60


def _get_api_key():
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    param_name = os.environ.get("ANTHROPIC_API_KEY_SSM_PARAM", DEFAULT_SSM_PARAM)
    return secrets.get_parameter(param_name)

SYSTEM_PROMPT = (
    "You assess a stock's current fundamentals for a retail investor "
    "research page, using only the metrics given to you. "
    "Classify the overall fundamental picture as 'Strong', 'Mixed', or "
    "'Weak', based on valuation, profitability, leverage and momentum. "
    "Write a two-to-three sentence factual summary of what the numbers "
    "show, in plain language a beginner understands. Separately list every "
    "specific weakness you notice (e.g. high debt, thin margins, weak "
    "momentum, rich valuation) as short phrases — an empty list only if "
    "there are genuinely none. If the summary mentions anything negative "
    "or soft about the stock, that same point must also appear in the "
    "weaknesses list — the two must never disagree. Never tell the reader "
    "to buy, sell, or hold, and "
    "never give a price target — assess and describe the fundamentals, "
    "don't recommend the stock. No preamble, no disclaimers, no markdown, "
    "plain sentences only in the summary."
)


def _build_prompt(symbol, header, fundamentals, ratios, eps_strength, price_strength):
    lines = [
        f"Stock: {header.get('name', symbol)} ({symbol})",
        f"Price: {header.get('price', '-')}, change {header.get('changePct', '-')} ({header.get('direction', '-')})",
    ]
    for f in fundamentals:
        lines.append(f"{f['label']}: {f['value']}")
    for r in ratios:
        lines.append(f"{r['label']}: {r['current']}")
    if eps_strength:
        lines.append(f"EPS Strength (1-99 percentile): {eps_strength}")
    if price_strength:
        lines.append(f"Price Strength (1-99 percentile): {price_strength}")
    return "\n".join(lines)


def _fetch(symbol, header, fundamentals, ratios, eps_strength, price_strength):
    if anthropic is None:
        raise RuntimeError("anthropic package is not installed")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("no Anthropic API key available (env var or SSM parameter)")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(symbol, header, fundamentals, ratios, eps_strength, price_strength)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=StockVerdict,
    )
    verdict = response.parsed_output
    if not verdict or not verdict.summary:
        raise RuntimeError("empty response from Claude")
    return {"label": verdict.label, "summary": verdict.summary, "weaknesses": verdict.weaknesses}


def get_verdict(symbol, header, fundamentals, ratios, eps_strength=None, price_strength=None):
    key = f"ai_verdict_{symbol.upper()}"
    return cache.get_or_fetch(
        key,
        CACHE_TTL_SECONDS,
        lambda: _fetch(symbol, header, fundamentals, ratios, eps_strength, price_strength),
    )
