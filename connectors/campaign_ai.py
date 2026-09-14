"""AI-generated copy for the admin's scanner-campaign notification builder
— given the admin's own free-text instruction plus the selected trade
ideas, today's date and the current market status, Claude writes a
notification title, header/intro line, and an entry-line template.

Self-contained (own API-key resolution) rather than importing from
connectors/ai_verdict.py — same reasoning as chart_connector.py's own note
on why it doesn't share a client with dhan_connector.py: different
concerns, kept independent rather than forcing a shared dependency.

Best-effort: if the `anthropic`/`pydantic` packages aren't installed, no
API key is available, or the call fails, the caller gets a RuntimeError and
should surface that as an error rather than silently falling back — unlike
ai_verdict.py's page-degrades-gracefully case, this is a deliberate
admin-initiated action ("Generate with AI"), so the admin needs to know it
didn't work rather than getting stale/blank fields with no explanation.
"""

import os

try:
    import anthropic
    from pydantic import BaseModel
except ImportError:
    anthropic = None
    BaseModel = object


if anthropic is not None:
    class CampaignCopy(BaseModel):
        title: str
        header: str
        entry_line_template: str
else:
    CampaignCopy = None

from connectors import secrets

MODEL = "claude-haiku-4-5-20251001"

DEFAULT_SSM_PARAM = "/chartink-momentum-ai/anthropic_api_key"

SYSTEM_PROMPT = (
    "You write push/in-app notification copy for Quantile, a stock-market "
    "signal service for Indian retail traders. Given the admin's own "
    "instruction, today's date, the current market status, and the "
    "specific trade ideas selected for this campaign, generate three "
    "pieces of copy:\n"
    "1. title: a short, punchy notification title (under 60 characters), "
    "optionally with 1-2 relevant emoji.\n"
    "2. header: a 1-3 sentence intro line that hooks the reader — "
    "energetic and attention-grabbing but still credible, no hype or "
    "spam, no promises of profit. May reference live market/chart status "
    "if the admin's instruction asks for that.\n"
    "3. entry_line_template: a template for one trade idea (usually one "
    "line, but two lines — separated by a real newline — is fine, e.g. "
    "when adding a 'View chart' call-to-action on its own line) that MUST "
    "literally contain the tokens {{symbol}}, {{entry}}, {{sl}}, "
    "{{target}} exactly as written (double curly braces, do NOT fill in "
    "real values — they get substituted per stock afterward). You may "
    "also include {{note}} if it fits naturally, and {{chart_url}} — a "
    "live link to that specific stock's chart page — if the admin's "
    "instruction asks for a chart link/CTA/button. When you use "
    "{{chart_url}}, you MUST wrap it in this exact Markdown-style syntax "
    "on its own line: [Label]({{chart_url}}) — e.g. '[📊 View Chart]"
    "({{chart_url}})'. This shows only the clean label to the reader "
    "(never the raw link) and still stays fully clickable — do NOT write "
    "{{chart_url}} bare or the URL will be shown as ugly plain text "
    "instead of a button.\n"
    "Tasteful emoji (e.g. 📈 🎯 🚀 ⚡ 🔔) are welcome in all three fields "
    "to make it visually engaging, but at most 1-2 per field — this is "
    "still a trading alert, not spam. Never claim guaranteed returns or "
    "give financial advice beyond the trade levels themselves. No "
    "markdown, plain text only."
)


def _get_api_key():
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    param_name = os.environ.get("ANTHROPIC_API_KEY_SSM_PARAM", DEFAULT_SSM_PARAM)
    return secrets.get_parameter(param_name)


def _build_prompt(instruction, entries, market_status, today):
    lines = [
        f"Today: {today}",
        f"Market status: {market_status}",
        "Admin's instruction: " + (instruction or "(none given — use good judgement for a general trade-alert campaign)"),
    ]
    if entries:
        lines.append("")
        lines.append("Selected trade ideas:")
        for e in entries:
            detail = f"- {e.get('symbol', '?')}"
            if e.get("type"):
                detail += f" ({e['type']})"
            detail += f": Entry {e.get('entry', '-')}, SL {e.get('sl', '-')}, Target {e.get('target', '-')}"
            if e.get("note"):
                detail += f", note: {e['note']}"
            lines.append(detail)
    else:
        lines.append("")
        lines.append("No specific trade ideas selected yet — write a generic template usable for any stock.")
    return "\n".join(lines)


def generate_campaign_copy(instruction, entries, market_status, today):
    """Returns {"title", "header", "entry_line_template"}. Raises
    RuntimeError on any failure — the admin's "Generate with AI" click is a
    deliberate action that should surface a clear error, not fail silently."""
    if anthropic is None:
        raise RuntimeError("the anthropic package is not installed")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("no Anthropic API key available (env var or SSM parameter)")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(instruction, entries, market_status, today)

    response = client.messages.parse(
        # No output_config/effort here — that parameter is Opus/Sonnet-5-
        # family only; Haiku rejects it with a 400.
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=CampaignCopy,
    )
    copy = response.parsed_output
    if not copy or not copy.title or not copy.entry_line_template:
        raise RuntimeError("empty response from Claude")
    return {"title": copy.title, "header": copy.header, "entry_line_template": copy.entry_line_template}
