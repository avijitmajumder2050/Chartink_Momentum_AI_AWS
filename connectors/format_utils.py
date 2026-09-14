"""Shared formatting helpers so connector output matches the exact
string/color conventions the templates already render (see mock_data.py).
"""

import datetime
import re

GREEN = "#17A673"
RED = "#E0473F"

TAG_PALETTE = {
    "IPO": {"tagColor": "#B98A2E", "tagBg": "#FBF2E1"},
    "ECONOMY": {"tagColor": "#4640DE", "tagBg": "#EEEDFD"},
    "CORPORATE": {"tagColor": "#E0473F", "tagBg": "#FCEBEA"},
    "GLOBAL": {"tagColor": "#5B6270", "tagBg": "#F0F1F4"},
    "MARKETS": {"tagColor": "#F2A93B", "tagBg": "#FBF2E1"},
}

THUMB_COLORS = ["#4640DE", "#17A673", "#B98A2E", "#14171F", "#E0473F"]


def initials(name):
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "??"


def pct_str(value):
    """-3.6 -> '-3.60%', 3.6 -> '+3.60%'"""
    value = float(value)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def change_color(value):
    return GREEN if float(value) >= 0 else RED


def inr_crores(value_in_crores):
    """12_800_000 rupees worth of crores -> '₹12.8 L Cr' style string.

    `value_in_crores` is already expressed in Crores (as scraped sites do).
    >= 1,00,000 Cr -> Lakh Cr, else plain Cr.
    """
    value_in_crores = float(value_in_crores)
    if abs(value_in_crores) >= 1_00_000:
        return f"₹{value_in_crores / 1_00_000:.2f} L Cr"
    return f"₹{value_in_crores:,.0f} Cr"


def sparkline_points(values, width=260, height=32):
    """[10, 12, 15, 13, 20] -> '0,22 65,15 ...' SVG polyline points,
    normalized into a `width` x `height` viewBox (matches the sparklines
    already used in research.html).
    """
    values = [float(v) for v in values]
    if not values:
        return ""
    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1
    n = len(values)
    step = width / (n - 1) if n > 1 else 0
    points = []
    for i, v in enumerate(values):
        x = i * step
        y = height - ((v - vmin) / span) * height
        points.append(f"{x:.0f},{y:.0f}")
    return " ".join(points)


def time_ago(dt):
    """datetime -> '3h ago' / '1d ago' style relative string."""
    if dt is None:
        return ""
    now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"
