import csv
import datetime
import decimal
import functools
import hashlib
import hmac
import io
import json
import math
import os
import random
import re
import string
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, Response, abort, jsonify, request, session

import chartink_daily_hammer as hammer_mod
import chartink_stoch_backtest as stoch_mod
import dhan_ema_breakout as dhan_ema_mod
import first_minute_movers as first_minute_mod
import mock_data
from connectors import ai_verdict, auth_verify, cache, campaign_ai, campaign_connector, chart_connector, cognito_connector, dhan_connector, fcm_connector, fundamentals_connector, ipo_connector, marketsmith_connector, news_connector, order_intent_connector, razorpay_connector, secrets, stock_screener_ai, subscription_connector
from connectors.format_utils import pct_str

app = Flask(__name__)
app.secret_key = secrets.get_parameter("/chartink-momentum-ai/flask_secret_key")
app.permanent_session_lifetime = datetime.timedelta(days=30)  # matches the Cognito app client's refresh-token validity
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Local-dev-only CORS for the React SPA (Vite's default port) hitting this
# API from a different origin — never enabled unless FLASK_DEBUG=1 is set
# explicitly, so a production deployment can't accidentally ship this open.
# (Checking os.environ directly rather than app.debug: app.debug is only
# True once app.run(debug=True) is actually called, further down this
# file — too late for a module-level CORS() setup that must run before any
# request is handled.) The SPA sends its own Authorization: Bearer
# <id_token> on every call (see _user_from_bearer_token below), so
# credentialed cookies aren't needed.
if os.environ.get("FLASK_DEBUG"):
    from flask_cors import CORS
    CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}})


# ============================================================
# AUTH (AWS Cognito)
# ============================================================

def _role_from_groups(groups):
    # Two roles: "admin" (explicit Cognito group membership) and
    # "subscriber" (everyone else who's signed in) — no separate
    # "subscriber" group membership is required, so self-signup users don't
    # need a Lambda trigger to get a usable role.
    return "admin" if "admin" in groups else "subscriber"


def _store_tokens(email, tokens):
    session.permanent = True
    session["email"] = email
    session["access_token"] = tokens["access_token"]
    session["id_token"] = tokens["id_token"]
    if tokens.get("refresh_token"):
        session["refresh_token"] = tokens["refresh_token"]
    claims = cognito_connector.decode_claims(tokens["id_token"])
    session["role"] = _role_from_groups(claims.get("cognito:groups", []))
    session["name"] = claims.get("name") or email.split("@")[0]
    # 60s safety margin so a request doesn't start with a token that expires
    # mid-flight.
    session["token_expires_at"] = time.time() + tokens["expires_in"] - 60


def _current_user_from_session():
    """Session-only check (no live Cognito call on every request) — the
    session cookie is signed with app.secret_key, so its contents can't be
    forged client-side; a stored access_token past its expiry is
    transparently refreshed via the stored refresh_token, or the session is
    cleared if that's also gone/invalid."""
    email = session.get("email")
    access_token = session.get("access_token")
    if not email or not access_token:
        return None

    if time.time() >= session.get("token_expires_at", 0):
        refresh_token = session.get("refresh_token")
        if not refresh_token:
            session.clear()
            return None
        try:
            tokens = cognito_connector.refresh_tokens(refresh_token, email)
        except cognito_connector.AuthError:
            session.clear()
            return None
        tokens.setdefault("refresh_token", refresh_token)
        _store_tokens(email, tokens)

    return {"email": email, "role": session.get("role", "subscriber"), "name": session.get("name", email.split("@")[0])}


def _user_from_bearer_token():
    """Verifies an `Authorization: Bearer <id_token>` header against
    Cognito (see connectors/auth_verify.py) — this is how the React SPA
    authenticates every API call, unlike the legacy Flask session cookie.
    Returns None (never raises) on a missing/invalid/expired token so
    callers can fall through to the session-cookie check."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):].strip()
    try:
        claims = auth_verify.verify_id_token(token)
    except auth_verify.TokenVerificationError:
        return None
    email = claims.get("email")
    if not email:
        return None
    return {
        "email": email,
        "role": _role_from_groups(claims.get("cognito:groups", [])),
        "name": claims.get("name") or email.split("@")[0],
    }


def _current_user():
    """Bearer-token check first (the SPA's auth path, verified fresh on
    every request), falling back to the legacy session-cookie check (any
    remaining server-rendered page, and the legacy /api/auth/login path) —
    both work side by side during the SPA migration so neither path breaks
    the other."""
    return _user_from_bearer_token() or _current_user_from_session()


def _is_api_request():
    # An unauthenticated /api/* call (from the React SPA, or anything else
    # calling the JSON API directly) needs a real 401/403 JSON response —
    # Historical note: this used to branch page routes (HTML redirect) vs
    # API routes (JSON error) — now that app.py is a pure JSON API (every
    # remaining decorated route is under /api/*, the React SPA is the only
    # frontend), login_required/role_required below always return JSON.
    return request.path.startswith("/api/")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if _current_user() is None:
            return jsonify({"error": "Not authenticated."}), 401
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Like login_required, but also requires the signed-in user's role to
    be one of `roles` — a wrong-role (but signed-in) user gets 403."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user is None:
                return jsonify({"error": "Not authenticated."}), 401
            if user["role"] not in roles:
                return jsonify({"error": "Forbidden."}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def subscription_required(view):
    """Like login_required, but also requires a paid plan (pro or
    premium) — admins always pass regardless of their own plan, same
    "admin can see everything" convention role_required already applies
    elsewhere. Gates the Markets sub-pages (IPO Hub, Stock Research,
    Scanner, Chart, Chart Wall) to paying subscribers server-side, not
    just via the frontend's RequireSubscription route guard — that guard
    alone wouldn't stop a signed-in free-plan user from calling these
    APIs directly."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = _current_user()
        if user is None:
            return jsonify({"error": "Not authenticated."}), 401
        if user["role"] != "admin":
            plan = subscription_connector.get_subscription(user["email"]).get("plan", "free")
            if plan not in ("pro", "premium"):
                return jsonify({"error": "This requires a Pro or Premium subscription."}), 403
        return view(*args, **kwargs)
    return wrapped


@app.get("/api/auth/me")
def api_auth_me():
    """Current signed-in identity for the React SPA — replaces what Jinja's
    inject_current_user() context processor gave server-rendered templates
    for free. Called once on app load (and after login) so the SPA knows
    who's signed in, their role, and their plan without needing a whole
    dashboard bootstrap just to render the header/nav correctly."""
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not authenticated."}), 401
    plan = subscription_connector.get_subscription(user["email"]).get("plan", "free")
    return jsonify({"email": user["email"], "name": user["name"], "role": user["role"], "plan": plan})


# The legacy self-service auth endpoints that used to live here (signup,
# confirm, resend-code, login, logout, forgot-password, reset-password —
# all session-cookie-based) were removed once Cognito Hosted UI's PKCE
# redirect flow (frontend/src/auth/pkce.js) was confirmed working
# end-to-end across every phase of the rewrite: the SPA never calls any
# of them (only GET /api/auth/me above), and they called url_for() on
# page routes (login, subscriber_dashboard) that no longer exist now that
# app.py is a pure JSON API. cognito_connector.sign_up/confirm_sign_up/
# resend_confirmation_code/sign_in/forgot_password/confirm_forgot_
# password still exist in the connector for admin-side use — only the
# HTTP endpoints that exposed them directly to a browser are gone.
#
# _current_user_from_session()/_store_tokens() (see _current_user() above)
# are effectively unreachable now too — nothing can ever populate a
# session cookie since api_auth_login was the only thing that called
# _store_tokens for a fresh login — left in place rather than removed in
# this pass since they're harmless and _current_user() still falls back
# to them safely (always None), but they're a known follow-up cleanup.


# ============================================================
# COLUMN / STAT HELPERS
# ============================================================

def _stat(label, value):
    return {"label": label, "value": value}


def _col(key, label, type_="text"):
    return {"key": key, "label": label, "type": type_}


# ============================================================
# SCANNER RUNNERS
#
# Each of these calls straight into the existing scanner
# scripts' functions - the backend re-runs the live Chartink
# request every time a scanner is selected, nothing here is
# precomputed or cached to disk for display purposes.
# ============================================================

def run_stoch():

    backtest_df = stoch_mod.get_backtest()
    live_df = stoch_mod.get_live_scan()

    if backtest_df is None or live_df is None:
        raise RuntimeError("Scanner did not return data")

    combined_df = stoch_mod.combine_live_and_backtest(
        live_df, backtest_df, days=10
    )

    rows = []

    if not combined_df.empty:
        rows = combined_df.rename(
            columns={"Backtest_Dates_Last_10": "BacktestDates"}
        ).to_dict(orient="records")

    return {
        "stats": [_stat("Match", len(live_df))],
        "columns": [
            _col("Stock", "Stock", "symbol"),
            _col("In_Live_Scan_Today", "In Live Scan", "bool"),
            _col("Price", "Price", "num"),
            _col("High", "High", "num"),
            _col("Low", "Low", "num"),
            _col("BacktestDates", "Backtest Dates (Last 10 Days)"),
        ],
        "rows": rows,
    }


def run_daily_hammer():

    backtest_df = hammer_mod.get_backtest()
    live_df = hammer_mod.get_live_scan()

    if backtest_df is None or live_df is None:
        raise RuntimeError("Scanner did not return data")

    combined_df = hammer_mod.combine_live_and_backtest(
        live_df, backtest_df, days=7
    )

    rows = []

    if not combined_df.empty:
        rows = combined_df.rename(
            columns={"Backtest_Dates_Last_7": "BacktestDates"}
        ).to_dict(orient="records")

    return {
        "stats": [_stat("Match", len(live_df))],
        "columns": [
            _col("Stock", "Stock", "symbol"),
            _col("In_Live_Scan_Today", "In Live Scan", "bool"),
            _col("Price", "Price", "num"),
            _col("High", "High", "num"),
            _col("Low", "Low", "num"),
            _col("BacktestDates", "Backtest Dates (Last 7 Days)"),
        ],
        "rows": rows,
    }


def run_dhan_ema_breakout():

    df = dhan_ema_mod.get_ema_breakout_matches()

    if df is None:
        raise RuntimeError("EMA breakout scan did not return data")

    rows = df.to_dict(orient="records") if not df.empty else []

    return {
        "stats": [_stat("Match", len(df))],
        "columns": [
            _col("Stock Name", "Stock", "symbol"),
            _col("Security ID", "Security ID"),
            _col("Market Cap", "Market Cap", "num"),
            _col("Open", "Open", "num"),
            _col("Price", "Price", "num"),
            _col("High", "High", "num"),
            _col("Low", "Low", "num"),
            _col("EPS Strength", "EPS Str", "num"),
            _col("Price Strength", "Price Str", "num"),
            _col("Setup_Case", "Setup"),
            _col("Scan Time", "Scan Time"),
        ],
        "rows": rows,
    }


def run_first_minute_movers():

    gainers_df, losers_df = first_minute_mod.get_first_minute_gainers_losers(top_n=10)

    if gainers_df.empty and losers_df.empty:
        raise RuntimeError("No first-candle data yet - try again shortly after market open (09:15 IST)")

    rows = gainers_df.to_dict(orient="records") + losers_df.to_dict(orient="records")
    candle_label = f"1st {first_minute_mod.INTERVAL_MINUTES}-min"

    return {
        "stats": [_stat("Gainers", len(gainers_df)), _stat("Losers", len(losers_df))],
        "columns": [
            _col("Stock Name", "Stock", "symbol"),
            _col("Type", "Type"),
            _col("Change %", "Change %", "pct"),
            _col("Prev Close", "Prev Close", "num"),
            _col("Open", f"Open ({candle_label})", "num"),
            _col("Close", f"Close ({candle_label})", "num"),
            _col("High", f"High ({candle_label})", "num"),
            _col("Low", f"Low ({candle_label})", "num"),
            _col("Volume", f"Volume ({candle_label})", "num"),
            _col("Day Volume", "Volume (day, so far)", "num"),
            _col("First Candle Time", "Candle Time"),
        ],
        "rows": rows,
    }


SCANNERS = {
    "stoch": {
        "name": "Stochastic Crossover",
        "description": (
            "%K/%D(4,3) cross above 20, RSI(14) below 50, close below "
            "EMA(50) — live scan combined with the last 10 backtest days"
        ),
        "run": run_stoch,
    },
    "daily_hammer": {
        "name": "Daily Hammer",
        "description": (
            "Yesterday's candle: hammer shape (lower shadow > 50% of "
            "range, body < 30% of range), close crossed above EMA20 or "
            "EMA50, with EMA10 >= EMA20 >= EMA50 >= EMA200 aligned — live "
            "scan combined with the last 7 backtest days"
        ),
        "run": run_daily_hammer,
    },
    "dhan_ema_breakout": {
        "name": "EMA 10/20 Breakout",
        "description": (
            "Price crossing above EMA10 or EMA20 today, with EMA10 > "
            "EMA20 > EMA50 aligned, market cap > 500cr, volume > 70,000, "
            "EPS Strength >= 80 and Price Strength >= 80 — reads mapping/"
            "EOD data from S3"
        ),
        "run": run_dhan_ema_breakout,
    },
    "first_minute_movers": {
        "name": "First 5-Min Candle Gainers/Losers",
        "description": (
            "Top 10 gainers and top 10 losers by % change of each stock's "
            "first 5-minute candle (09:15-09:20 IST) vs the previous "
            "session's close, restricted to a first-candle volume above "
            "20,000 — an early read on opening momentum in actively-"
            "traded names, not a full-day scan"
        ),
        "run": run_first_minute_movers,
    },
}

# Scan results are cached rather than re-run on every request — running a
# scanner re-hits the live upstream source (Chartink or the S3 EOD dump),
# which is slow and doesn't change meaningfully within a few minutes.
SCAN_CACHE_TTL_SECONDS = 5 * 60


# ============================================================
# Page-rendering routes lived here through the rewrite (home, /scanner,
# /news, /capabilities, /education, /pricing, /vision, /markets/ipo-hub) —
# all removed once their React equivalents (frontend/src/pages/*) shipped
# and were verified; app.py is a pure JSON API now. Their business logic
# (news_connector/ipo_connector calls, mock_data-backed static content)
# lives on in GET /api/news and GET /api/ipo-hub below; Home/Capabilities/
# Education/Pricing/Vision were static-in-React from the start (see the
# mock_data.py decision in the Phase 4 commit) so had no API equivalent
# to begin with. /scanner's logic was trivial (validate ?id= against
# SCANNERS) and is now just inline in the React Scanner page calling the
# already-existing GET /api/scanners.
# ============================================================


def _normalize_symbol(raw):
    # NSE/BSE tickers never contain spaces, so "HDFC Bank" -> "HDFCBANK"
    # and "TATA STEEL" -> "TATASTEEL" resolve correctly on screener.in
    # even though users naturally type the company name with spaces.
    return (raw or "HDFCBANK").strip().upper().replace(" ", "")


POPULAR_INDICES = ["NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA"]

# The /markets/research and /markets/chart page routes that used to live
# here were removed once their React equivalents shipped — their logic
# now lives on in GET /api/research and GET /api/chart/bootstrap below
# (which were written to mirror them exactly before this removal).


NEWS_MOVERS_LIMIT = 5


def _news_movers():
    """Live gainers/losers for the News page's Market movers card, from
    the dashboard's own cached watchlist metrics. peek(), not
    _dashboard_watchlist_metrics(): /api/news is public, and a cold-cache
    watchlist scan is ~350 S3/Dhan calls — this page should never be the
    thing that triggers one. Empty (card hidden) until the dashboard has
    populated it."""
    entry = cache.peek("dashboard_watchlist_metrics")
    metrics = (entry or {}).get("data") or []
    as_row = lambda m: {"symbol": m["symbol"], "change": pct_str(m["changePct"]), "price": m.get("price")}
    return {
        "gainers": [as_row(m) for m in _top_gainers(metrics, NEWS_MOVERS_LIMIT) if m["changePct"] > 0],
        "losers": [as_row(m) for m in _top_losers(metrics, NEWS_MOVERS_LIMIT) if m["changePct"] < 0],
        "moversUpdatedAt": datetime.datetime.fromtimestamp(entry["cached_at"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if metrics else None,
    }


HOME_INDICES = [
    ("NIFTY 50", "NIFTY 50"),
    ("SENSEX", "SENSEX"),
    ("BANK NIFTY", "BANK NIFTY"),
    ("NIFTY IT", "NIFTY IT"),
    ("NIFTYMIDSMALLCAP400", "MIDCAP 400"),
    ("INDIA VIX", "INDIA VIX"),
]
HOME_MOVERS_LIMIT = 4
WATCHLIST_METRICS_TTL_SECONDS = 15 * 60

_home_warm_lock = threading.Lock()


def _fetch_home_indices():
    results = []
    for symbol, label in HOME_INDICES:
        try:
            bars = chart_connector.get_ohlcv(symbol)
        except Exception:
            continue
        if len(bars) < 2 or not bars[-2]["close"]:
            continue
        last, prev = bars[-1]["close"], bars[-2]["close"]
        results.append({"label": label, "value": last, "change": last - prev, "changePct": (last - prev) / prev * 100})
    return results


def _warm_watchlist_metrics_in_background():
    """Kick off a watchlist scan without waiting for it — at most one at a
    time (non-blocking lock), and only when the cached result is missing
    or expired, so the public homepage costs at most one scan per cache
    window no matter how many people visit."""
    if not _home_warm_lock.acquire(blocking=False):
        return

    def run():
        try:
            _dashboard_watchlist_metrics()
        except Exception:
            app.logger.exception("background watchlist metrics warm failed")
        finally:
            _home_warm_lock.release()

    threading.Thread(target=run, daemon=True).start()


@app.get("/api/home")
def api_home():
    """Live market data for the public homepage: index strip, today's top
    movers and market breadth. Indices are fetched directly (a handful of
    cached quotes); movers/breadth reuse the dashboard's watchlist scan
    via peek() and refresh it in the background rather than making a
    visitor wait ~16s for it."""
    try:
        indices = cache.get_or_fetch("home_market_indices", 5 * 60, _fetch_home_indices)
    except Exception:
        app.logger.exception("home indices failed")
        indices = []

    entry = cache.peek("dashboard_watchlist_metrics")
    if not entry or time.time() - entry.get("cached_at", 0) > WATCHLIST_METRICS_TTL_SECONDS:
        _warm_watchlist_metrics_in_background()
    metrics = (entry or {}).get("data") or []
    as_row = lambda m: {"symbol": m["symbol"], "price": m.get("price"), "changePct": m["changePct"]}

    return jsonify({
        "indices": indices,
        "gainers": [as_row(m) for m in _top_gainers(metrics, HOME_MOVERS_LIMIT) if m["changePct"] > 0],
        "losers": [as_row(m) for m in _top_losers(metrics, HOME_MOVERS_LIMIT) if m["changePct"] < 0],
        "breadth": _breadth_from_metrics(metrics),
        "moversUpdatedAt": datetime.datetime.fromtimestamp(entry["cached_at"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if metrics else None,
    })


@app.get("/api/news")
def api_news():
    try:
        data = news_connector.get_news_data()
    except Exception:
        app.logger.exception("news connector failed")
        data = {"stories": [], "orderWins": [], "trending": [], "unavailable": True}
    try:
        data.update(_news_movers())
    except Exception:
        app.logger.exception("news movers failed")
        data.update(gainers=[], losers=[], moversUpdatedAt=None)
    return jsonify(data)


@app.get("/api/ipo-hub")
@subscription_required
def api_ipo_hub():
    try:
        data = ipo_connector.get_ipo_hub_data()
    except Exception:
        app.logger.exception("IPO connector failed")
        data = {"ipos": [], "subCategories": [], "unavailable": True}
    return jsonify(data)


@app.get("/api/watchlist")
@subscription_required
def api_watchlist():
    """Was only ever baked into server-rendered chart_wall.html before —
    same fetch chart_wall_page() used, now available standalone."""
    try:
        stocks = chart_connector.get_watchlist_stocks_cached()
    except Exception:
        app.logger.exception("chart wall stock list fetch failed")
        return jsonify({"watchlist": [], "unavailable": True})
    return jsonify({"watchlist": stocks, "unavailable": False})


@app.get("/api/research")
@subscription_required
def api_research():
    """Mirrors research()'s exact orchestration (4 connectors, layered
    best-effort fallbacks) as JSON instead of a render — same flat shape
    Jinja already consumed via simple truthiness checks (epsStrength,
    priceHistory, aiVerdict etc. just absent when that best-effort step
    failed), rather than inventing a new nested "sections" wrapper."""
    symbol = _normalize_symbol(request.args.get("symbol"))
    try:
        data = fundamentals_connector.get_research_data(symbol)
        data.update(fundamentals_connector.get_fundamentals_data(symbol))
    except RuntimeError:
        return jsonify({"symbol": symbol, "notFound": True})
    except Exception:
        app.logger.exception("fundamentals connector failed for %s", symbol)
        return jsonify({"symbol": symbol, "unavailable": True})

    try:
        data.update(marketsmith_connector.get_strength_ratings(symbol))
    except Exception:
        app.logger.exception("marketsmith connector failed for %s", symbol)

    try:
        data["priceHistory"] = fundamentals_connector.get_price_history(symbol)
    except Exception:
        app.logger.exception("price history fetch failed for %s", symbol)

    try:
        data["aiVerdict"] = ai_verdict.get_verdict(
            symbol,
            data.get("header", {}),
            data.get("fundamentals", []),
            data.get("ratios", []),
            data.get("epsStrength"),
            data.get("priceStrength"),
        )
    except Exception:
        app.logger.exception("AI verdict generation failed for %s", symbol)

    data["symbol"] = symbol
    return jsonify(data)


@app.get("/api/chart/bootstrap")
@subscription_required
def api_chart_bootstrap():
    """Symbol-list + default-symbol resolution for the Chart page — was
    only ever inline in chart_page() before; /api/chart/data (below)
    still handles the actual bar data for a chosen symbol."""
    try:
        symbols = chart_connector.get_top_symbols_cached(limit=200)
    except Exception:
        app.logger.exception("chart symbol list fetch failed")
        symbols = []
    requested = _normalize_symbol(request.args.get("symbol")) if request.args.get("symbol") else None
    default_symbol = requested or (symbols[0]["symbol"] if symbols else None)
    return jsonify({"symbols": symbols, "indices": POPULAR_INDICES, "defaultSymbol": default_symbol})


@app.get("/api/chart/data")
@subscription_required
def api_chart_data():
    symbol = _normalize_symbol(request.args.get("symbol"))
    try:
        bars = chart_connector.get_ohlcv(symbol)
    except LookupError:
        return jsonify({"error": f"No chart data for {symbol}"}), 404
    except Exception as exc:
        app.logger.exception("chart data fetch failed for %s", symbol)
        return jsonify({"error": str(exc)}), 502
    return jsonify({"symbol": symbol, "bars": bars})


# /markets/chart-wall, /login, /payment (a dead redirect even in the
# original app — see the rewrite plan) and /subscription's page routes
# were removed here — chart-wall's logic lives on in GET /api/watchlist,
# subscription's in GET /api/subscription/bootstrap (both below), login
# is Cognito Hosted UI now, and /payment had nowhere left to forward to.


@app.get("/api/subscription/bootstrap")
@login_required
def api_subscription_bootstrap():
    """Bootstrap data for the Subscription page — was only ever inline
    in subscription_page() before; checkout/cancel/redeem-voucher
    (below) already were JSON and stay as-is."""
    user = _current_user()
    sub = subscription_connector.get_subscription(user["email"])
    return jsonify(_json_safe({
        "subscription": sub,
        "plans": subscription_connector.PLANS,
        "campaigns": subscription_connector.list_visible_campaigns(),
        "razorpay": {
            "configured": razorpay_connector.is_configured(),
            "keyId": (secrets.get_parameter("/chartink-momentum-ai/razorpay/key_id") if razorpay_connector.is_configured() else None),
        },
    }))


@app.post("/api/subscription/redeem-voucher")
@login_required
def api_subscription_redeem_voucher():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan")
    code = data.get("code")
    try:
        sub = subscription_connector.redeem_voucher(user["email"], plan_id, code)
    except subscription_connector.PartialDiscountVoucher as partial:
        return jsonify({"ok": True, "requiresCheckout": True, "percentOff": partial.campaign["percent_off"]})
    except subscription_connector.SubscriptionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "subscription": {k: v for k, v in sub.items() if k != "history"}})


@app.post("/api/subscription/checkout")
@login_required
def api_subscription_checkout():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan")
    code = data.get("code")
    if plan_id not in ("pro", "premium"):
        return jsonify({"error": "Choose a paid plan."}), 400
    if not razorpay_connector.is_configured():
        return jsonify({"error": "Card/UPI checkout isn't set up yet — use a voucher code, or contact us."}), 503

    discount = None
    if code:
        try:
            campaign = subscription_connector.check_campaign_eligibility(code, plan_id)
        except subscription_connector.SubscriptionError as exc:
            return jsonify({"error": str(exc)}), 400
        plan = subscription_connector.PLANS[plan_id]
        discount = {
            "percent_off": campaign["percent_off"],
            "base_price_paise": plan["price_paise"],
            "plan_name": plan["name"],
            "voucher_code": campaign["code"],
        }

    try:
        rp_sub = razorpay_connector.create_subscription(plan_id, user["email"], user["name"], discount=discount)
    except razorpay_connector.RazorpayError as exc:
        app.logger.exception("Razorpay subscription creation failed")
        return jsonify({"error": str(exc)}), 502
    return jsonify({
        "ok": True,
        "razorpay_subscription_id": rp_sub["id"],
        "razorpay_key_id": secrets.get_parameter("/chartink-momentum-ai/razorpay/key_id"),
        "plan": plan_id,
    })


@app.post("/api/subscription/checkout/confirm")
@login_required
def api_subscription_checkout_confirm():
    """Called from Checkout.js's success handler with the three values
    Razorpay hands back — verified here before the plan is ever marked
    active, so a tampered client-side response can't grant a free
    upgrade. The subscription.activated webhook (once configured) is the
    durable source of truth; this just gives the user instant feedback
    without waiting on webhook delivery."""
    user = _current_user()
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan")
    code = data.get("code")
    rp_subscription_id = data.get("razorpay_subscription_id")
    rp_payment_id = data.get("razorpay_payment_id")
    rp_signature = data.get("razorpay_signature")

    if not all([plan_id, rp_subscription_id, rp_payment_id, rp_signature]):
        return jsonify({"error": "Incomplete payment confirmation."}), 400

    if not razorpay_connector.verify_payment_signature(rp_subscription_id, rp_payment_id, rp_signature):
        return jsonify({"error": "Payment could not be verified."}), 400

    try:
        rp_sub = razorpay_connector.fetch_subscription(rp_subscription_id)
    except razorpay_connector.RazorpayError as exc:
        return jsonify({"error": str(exc)}), 502

    current_period_end = None
    if rp_sub.get("current_end"):
        current_period_end = datetime.datetime.fromtimestamp(rp_sub["current_end"], tz=datetime.timezone.utc).replace(tzinfo=None).isoformat()

    sub = subscription_connector.apply_razorpay_subscription(
        user["email"], plan_id, rp_subscription_id, rp_sub.get("customer_id"), current_period_end, voucher_code=code,
    )
    if code:
        subscription_connector.record_voucher_redemption(code)
    return jsonify({"ok": True, "subscription": {k: v for k, v in sub.items() if k != "history"}})


@app.post("/api/subscription/cancel")
@login_required
def api_subscription_cancel():
    user = _current_user()
    try:
        sub = subscription_connector.cancel_subscription(user["email"])
    except subscription_connector.SubscriptionError as exc:
        return jsonify({"error": str(exc)}), 400

    rp_id = sub.get("razorpay_subscription_id")
    if rp_id:
        try:
            razorpay_connector.cancel_subscription(rp_id)
        except razorpay_connector.RazorpayError:
            app.logger.exception("Razorpay cancel failed for %s — local record already marked canceled", rp_id)

    return jsonify({"ok": True, "subscription": {k: v for k, v in sub.items() if k != "history"}})


@app.post("/api/webhooks/razorpay")
def api_webhook_razorpay():
    if not razorpay_connector.is_configured():
        abort(503)

    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature")
    try:
        valid = razorpay_connector.verify_webhook_signature(raw_body, signature)
    except Exception:
        abort(503)  # webhook_secret not set up yet (see setup_razorpay.py)
    if not valid:
        abort(400)

    event = request.get_json(silent=True) or {}
    event_type = event.get("event")
    entity = event.get("payload", {}).get("subscription", {}).get("entity", {})
    notes = entity.get("notes") or {}
    email = notes.get("email")
    plan_id = notes.get("internal_plan_id")
    voucher_code = notes.get("voucher_code")

    if not email or not plan_id:
        return jsonify({"ok": True})  # not a subscription event this app tracks — ack and ignore

    if event_type in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        current_period_end = (
            datetime.datetime.fromtimestamp(entity["current_end"], tz=datetime.timezone.utc).replace(tzinfo=None).isoformat()
            if entity.get("current_end") else None
        )
        subscription_connector.apply_razorpay_subscription(email, plan_id, entity["id"], entity.get("customer_id"), current_period_end, voucher_code=voucher_code)
    elif event_type in ("subscription.cancelled", "subscription.completed"):
        try:
            subscription_connector.cancel_subscription(email)
        except subscription_connector.SubscriptionError:
            pass  # already canceled locally — webhook arrived after our own cancel call
    elif event_type == "subscription.halted":
        subscription_connector.mark_past_due(email)

    return jsonify({"ok": True})


NSE_OPEN = datetime.time(9, 15)
NSE_CLOSE = datetime.time(15, 30)


def _market_status():
    now = datetime.datetime.now(chart_connector.IST)
    if now.weekday() < 5 and NSE_OPEN <= now.time() <= NSE_CLOSE:
        close_dt = now.replace(hour=15, minute=30, second=0, microsecond=0)
        remaining = int((close_dt - now).total_seconds())
        return f"Markets open · closes in {remaining // 3600}h {(remaining % 3600) // 60}m"
    return "Markets closed"


# Dashboard "market status" strip — real index quotes (live quote merged
# onto EOD history, same connectors/chart_connector.get_ohlcv() path the
# chart page itself uses). NIFTYMIDSMALLCAP400 is the actual index name
# for what's commonly just called "Midcap 400".
DASHBOARD_INDICES = [
    ("NIFTY 50", "NIFTY 50"),
    ("NIFTYMIDSMALLCAP400", "Midcap 400"),
    ("INDIA VIX", "India VIX"),
]

SECTOR_INDICES = [
    ("NIFTY IT", "IT"),
    ("BANK NIFTY", "Bank"),
    ("NIFTY AUTO", "Auto"),
    ("NIFTY FMCG", "FMCG"),
    ("NIFTY PHARMA", "Pharma"),
]

# Market breadth needs an up/down count across the whole tracked
# watchlist (~356 stocks), not just the handful shown in the Watchlist
# card. Earlier this was capped at 30 — a workaround for what turned out
# to be a real bug (chart_connector._get_live_quotes_batch() re-parsing
# its cache file on every concurrent call with no lock, serializing
# under the GIL); with that fixed, all ~356 stocks classify in ~16s at
# 25-way concurrency — no cap needed, generous headroom kept in case the
# watchlist grows. Loaded in the background regardless (see
# /api/dashboard/market-snapshot), never blocking the page, and the
# AGGREGATE result is itself cached (see _dashboard_market_breadth) so
# this cost is paid once per cache window, not once per page view.
BREADTH_SAMPLE_SIZE = 1000


def _symbol_change_pct(symbol):
    """Latest close vs the prior close, for any stock or index symbol
    get_ohlcv() can resolve. None if there's not enough history."""
    bars = chart_connector.get_ohlcv(symbol)
    if len(bars) < 2:
        return None
    last, prev = bars[-1], bars[-2]
    change_pct = ((last["close"] - prev["close"]) / prev["close"] * 100) if prev["close"] else 0
    return {"value": last["close"], "changePct": change_pct}


def _fetch_market_indices():
    results = []
    for symbol, label in DASHBOARD_INDICES:
        try:
            change = _symbol_change_pct(symbol)
            if change:
                results.append({"label": label, **change})
        except Exception:
            continue
    return results


def _dashboard_market_indices():
    # Short TTL — these are index levels, worth refreshing often — but
    # still avoids re-fetching on every single dashboard view within a
    # few minutes of each other.
    return cache.get_or_fetch("dashboard_market_indices", 5 * 60, _fetch_market_indices)


def _fetch_sector_momentum():
    results = []
    for symbol, label in SECTOR_INDICES:
        try:
            change = _symbol_change_pct(symbol)
            if change:
                results.append({"label": label, "changePct": change["changePct"]})
        except Exception:
            continue
    results.sort(key=lambda s: s["changePct"], reverse=True)
    return results


def _dashboard_sector_momentum():
    return cache.get_or_fetch("dashboard_sector_momentum", 15 * 60, _fetch_sector_momentum)


def _watchlist_stock_metrics(symbol):
    """change%, latest price, and volume-vs-its-own-20-day-average for one
    symbol — the per-stock building block shared by market breadth, top
    gainers/losers, and volume shockers (see _fetch_watchlist_metrics), so
    a single full-universe pass serves all four instead of one scan each."""
    bars = chart_connector.get_ohlcv(symbol)
    if len(bars) < 2:
        return None
    last, prev = bars[-1], bars[-2]
    # A real, trading stock never legitimately prints a close of exactly
    # 0 — that's a bad/missing upstream bar (e.g. a stale or corrupted
    # row), not a genuine -100% move, and would otherwise sit at the top
    # of "biggest losers" looking like a real (alarming) signal.
    if last["close"] <= 0 or prev["close"] <= 0:
        return None
    change_pct = (last["close"] - prev["close"]) / prev["close"] * 100

    volumes = [b["volume"] for b in bars]
    prior_volumes = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    avg_volume = (sum(prior_volumes) / len(prior_volumes)) if prior_volumes else None
    volume_ratio = (volumes[-1] / avg_volume) if avg_volume else None

    # Precise circuit status straight from Dhan's own upper/lower_circuit_
    # limit fields (see chart_connector.get_live_circuit_status) when a
    # live quote is available — None (unknown, not "not at circuit") when
    # it isn't, e.g. outside market hours; _is_circuit_locked() falls back
    # to a change%-based heuristic in that case.
    at_circuit = None
    try:
        instrument_id = chart_connector.get_symbol_mapping().get(symbol)
        if instrument_id is not None:
            circuit = chart_connector.get_live_circuit_status(instrument_id)
            if circuit:
                at_circuit = circuit["at_circuit"]
    except Exception:
        at_circuit = None

    return {
        "symbol": symbol,
        "price": last["close"],
        "changePct": change_pct,
        "volume": volumes[-1],
        "volumeRatio": volume_ratio,
        "atCircuit": at_circuit,
    }


def _fetch_watchlist_metrics():
    """One full concurrent pass across this app's own tracked watchlist
    universe (~356 stocks) — not the full NSE (there's no full-market
    data feed here to draw that from), scoped honestly to what's actually
    available rather than faked at "whole market" scale. Shared source
    for market breadth, top gainers/losers, and volume shockers, so this
    (real, non-trivial) cost is paid once, not once per section.

    Fetched concurrently (ThreadPoolExecutor, I/O-bound S3/Dhan calls) —
    measured at ~16s for all ~356 symbols at 25-way concurrency once
    chart_connector._get_live_quotes_batch()'s missing lock (real bug:
    concurrent calls each redundantly re-fetched/re-parsed instead of
    sharing one result) was fixed; before that fix the same workload
    would have been drastically slower. Still fully async regardless —
    never blocks a page load — and the result is itself cached (see
    _dashboard_watchlist_metrics)."""
    try:
        stocks = chart_connector.get_watchlist_stocks_cached()
    except Exception:
        return []

    sample = stocks[:BREADTH_SAMPLE_SIZE]

    def classify(stock):
        try:
            return _watchlist_stock_metrics(stock["symbol"])
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(classify, sample))

    return [r for r in results if r is not None]


def _dashboard_watchlist_metrics():
    return cache.get_or_fetch("dashboard_watchlist_metrics", 15 * 60, _fetch_watchlist_metrics)


def _breadth_from_metrics(metrics):
    if not metrics:
        return None
    advancing = sum(1 for m in metrics if m["changePct"] > 0.05)
    declining = sum(1 for m in metrics if m["changePct"] < -0.05)
    unchanged = len(metrics) - advancing - declining
    return {"advancing": advancing, "declining": declining, "unchanged": unchanged, "sampleSize": len(metrics)}


# Fallback only for when a metric has no live quote to check against
# (atCircuit is None — outside market hours, quote fetch failed, etc.):
# a stock frozen at its circuit trades at exactly prevClose * 1.05 (or
# * 0.95), so a change% suspiciously close to exactly +/-5.00% is that
# signature even without Dhan's own upper/lower_circuit_limit fields to
# confirm it directly (see chart_connector.get_live_circuit_status,
# which IS precise and is preferred whenever it's available).
CIRCUIT_LIMIT_PCT = 5.0
CIRCUIT_TOLERANCE_PCT = 0.15


def _is_circuit_locked(metric):
    at_circuit = metric.get("atCircuit")
    if at_circuit is not None:
        return at_circuit in ("upper", "lower")
    return abs(abs(metric["changePct"]) - CIRCUIT_LIMIT_PCT) <= CIRCUIT_TOLERANCE_PCT


def _exclude_circuit_locked(metrics):
    return [m for m in metrics if not _is_circuit_locked(m)]


def _top_gainers(metrics, limit=10):
    return sorted(_exclude_circuit_locked(metrics), key=lambda m: m["changePct"], reverse=True)[:limit]


def _top_losers(metrics, limit=10):
    return sorted(_exclude_circuit_locked(metrics), key=lambda m: m["changePct"])[:limit]


def _volume_shockers(metrics, limit=10):
    """Stocks trading at an unusually high multiple of their own 20-day
    average volume — the standard definition of a "volume shocker"."""
    ranked = sorted((m for m in _exclude_circuit_locked(metrics) if m.get("volumeRatio")), key=lambda m: m["volumeRatio"], reverse=True)
    return ranked[:limit]


def _dashboard_recent_alerts(plan, limit=3):
    """Same plan-based audience filtering as GET /api/notifications/recent
    — the dashboard's own view of that same feed, just a shorter list."""
    items = campaign_connector.list_recent_notifications(limit=30)
    items = [n for n in items if plan in (n.get("audience") or ["free", "pro", "premium"])]
    return items[:limit]


def _fetch_dashboard_watchlist(limit=10):
    """Real top-RS-Rating watchlist stocks with real live price/change —
    not "holdings": this app has no brokerage integration, so there's no
    real owned-shares/portfolio-value data to show, and fabricating some
    would be exactly the kind of mock data this page shouldn't have.

    Fetched concurrently — measured at ~6.85s sequentially for just 5
    stocks (each get_ohlcv is its own S3/Dhan round trip), which was most
    of what was left blocking the dashboard once market indices/sector/
    breadth moved off the page-load path entirely."""
    try:
        stocks = chart_connector.get_watchlist_stocks_cached()
    except Exception:
        return []

    ranked = sorted(
        (s for s in stocks if s.get("rsRating") is not None),
        key=lambda s: s["rsRating"],
        reverse=True,
    )[:limit]

    def fetch_row(stock):
        try:
            bars = chart_connector.get_ohlcv(stock["symbol"])
            if len(bars) < 2:
                return None
            last, prev = bars[-1], bars[-2]
            change_pct = ((last["close"] - prev["close"]) / prev["close"] * 100) if prev["close"] else 0
            return {"symbol": stock["symbol"], "price": last["close"], "changePct": change_pct}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max(1, len(ranked))) as pool:
        rows = list(pool.map(fetch_row, ranked))
    return [r for r in rows if r is not None]


def _dashboard_watchlist(limit=10):
    # Unlike _dashboard_watchlist_metrics() right below (cached 15 min),
    # this ran fresh on every single /api/dashboard/bootstrap call — 10
    # concurrent get_ohlcv() calls' worth of work paid on every dashboard
    # load even back-to-back, instead of once per TTL window like the
    # rest of the page. Same TTL as the market-snapshot metrics for
    # consistency — both already tolerate quotes up to that stale.
    return cache.get_or_fetch(f"dashboard_watchlist_{limit}", 15 * 60, lambda: _fetch_dashboard_watchlist(limit))


def _dashboard_scan_results(limit=4):
    """Last cached EMA 10/20 Breakout result, if the scanner has been run
    at least once — read-only (cache.peek), same as the scanner page's own
    "show cached, don't auto-run" behavior. None if it's never been run."""
    entry = cache.peek(_scanner_cache_key("dhan_ema_breakout"))
    if not entry:
        return None
    return {
        "rows": entry["data"].get("rows", [])[:limit],
        "generated_at": datetime.datetime.fromtimestamp(entry["cached_at"], tz=chart_connector.IST).strftime("%d %b, %I:%M %p"),
    }


def _cached_member_since(email):
    """An account's creation date never changes once set, so this is safe
    to cache for a long time — was previously a live Cognito API call on
    every single dashboard load (~1.9s) for a value that's permanently
    the same answer per user."""
    formatted = cache.get_or_fetch(
        f"member_since_{email}",
        7 * 24 * 60 * 60,
        lambda: cognito_connector.get_account_created_at(email).strftime("%d %b %Y"),
    )
    return formatted


@app.get("/api/dashboard/bootstrap")
@login_required
def api_dashboard_bootstrap():
    """The fast, synchronous part of the dashboard — was only ever inline
    in subscriber_dashboard() before. Market indices/sector-momentum/
    breadth deliberately stay out of this endpoint and out of the page
    load entirely — see /api/dashboard/market-snapshot below, unchanged,
    still fetched separately/concurrently after the page renders."""
    user = _current_user()
    data = {
        "today": datetime.datetime.now(chart_connector.IST).strftime("%A, %d %b %Y"),
        "marketStatus": _market_status(),
        "watchlist": _dashboard_watchlist(),
        "scanResults": _dashboard_scan_results(),
        "educationCourses": [
            c for c in mock_data.education_data()["courses"]
            if c["title"] in ("Technical Analysis Foundations", "IPO Investing Playbook")
        ],
    }
    try:
        data["memberSince"] = _cached_member_since(user["email"])
    except Exception:
        data["memberSince"] = None
    data["subscription"] = subscription_connector.get_subscription(user["email"])
    data["recentAlerts"] = _dashboard_recent_alerts(data["subscription"]["plan"])
    return jsonify(_json_safe(data))


@app.get("/api/dashboard/market-snapshot")
@login_required
def api_dashboard_market_snapshot():
    # Indices/sectors/watchlist-metrics are each independently cached (see
    # their own get_or_fetch calls), but on a cold cache they're each a
    # real, separate round of S3/Dhan calls — running them concurrently
    # rather than one after another means the page waits for the SLOWEST
    # of the three (the watchlist scan, ~16s worst case) instead of the
    # sum of all three. Breadth/gainers/losers/shockers all derive from
    # that one shared watchlist-metrics fetch rather than each re-scanning
    # the whole universe themselves.
    with ThreadPoolExecutor(max_workers=3) as pool:
        indices_f = pool.submit(_dashboard_market_indices)
        sectors_f = pool.submit(_dashboard_sector_momentum)
        metrics_f = pool.submit(_dashboard_watchlist_metrics)
        indices = indices_f.result()
        sector_momentum = sectors_f.result()
        metrics = metrics_f.result()

    return jsonify({
        "indices": indices,
        "sectorMomentum": sector_momentum,
        "breadth": _breadth_from_metrics(metrics) or {},
        "topGainers": _top_gainers(metrics),
        "topLosers": _top_losers(metrics),
        "volumeShockers": _volume_shockers(metrics),
    })


def _json_safe(obj):
    # Recursive version of _entry_json_safe's Decimal->float conversion,
    # for responses with nested dicts/lists (e.g. subscription bootstrap's
    # campaign list, where DynamoDB hands back Decimal for percent_off/
    # redemption_count) — jsonify() can't encode Decimal at any depth.
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _entry_json_safe(entry):
    # DynamoDB hands price fields back as decimal.Decimal (it rejects plain
    # float on the way in, see campaign_connector._to_decimal) — Flask's
    # jsonify() doesn't know how to encode Decimal, so convert for any
    # response that goes through jsonify (Jinja templates render Decimal
    # fine as-is and don't need this).
    return {
        k: (float(v) if isinstance(v, decimal.Decimal) else v)
        for k, v in entry.items()
    }


def _user_with_subscription(user):
    sub = subscription_connector.get_subscription(user["email"])
    user["plan"] = sub["plan_details"]["name"]
    user["sub_status"] = sub["status"]
    return user


ADMIN_USERS_CACHE_TTL_SECONDS = 30
_admin_users_cache = None  # (cached_at, users) — in-process, not connectors/cache.py's
# file-based cache: list_all_users() hands back real datetime objects in
# created_at (only isoformat'd later, per user, in _users_with_subscriptions),
# and that cache's JSON backing store can't serialize those.
_admin_users_lock = threading.Lock()


def _cached_list_all_users():
    # list_all_users() is 2 real Cognito API calls (~2s+ measured here) —
    # worth a short cache given both admin pages below call it on every
    # load. Kept short, and explicitly invalidated by every mutation
    # endpoint below (create/role/enabled/delete), because the frontend
    # already refetches right after each of those — a longer TTL with no
    # invalidation would make an admin's own change look like it silently
    # didn't take effect until the cache expired.
    global _admin_users_cache
    if _admin_users_cache is not None:
        cached_at, users = _admin_users_cache
        if time.time() - cached_at < ADMIN_USERS_CACHE_TTL_SECONDS:
            return users
    with _admin_users_lock:
        if _admin_users_cache is not None:
            cached_at, users = _admin_users_cache
            if time.time() - cached_at < ADMIN_USERS_CACHE_TTL_SECONDS:
                return users
        users = cognito_connector.list_all_users()
        _admin_users_cache = (time.time(), users)
        return users


def _invalidate_admin_users_cache():
    global _admin_users_cache
    _admin_users_cache = None


def _users_with_subscriptions(users):
    # Was a plain sequential loop — one subscription_connector.get_subscription()
    # DynamoDB round trip per user, one at a time. Fine at today's handful
    # of users, but scales linearly with the user base for no reason —
    # each lookup is independent I/O, same shape as the watchlist's own
    # concurrent per-symbol fetches.
    def build(u):
        u = _user_with_subscription(dict(u))
        u["created_at"] = u["created_at"].isoformat()
        return u

    with ThreadPoolExecutor(max_workers=min(20, max(1, len(users)))) as pool:
        return list(pool.map(build, users))


@app.get("/api/admin/dashboard")
@role_required("admin")
def api_admin_dashboard():
    """Mirrors the logic the removed admin_dashboard() page route used to
    do inline."""
    users = _cached_list_all_users()
    stats = subscription_connector.compute_revenue_stats(len(users))
    admin_count = sum(1 for u in users if u["role"] == "admin")
    recent_users = _users_with_subscriptions(users[:6])

    return jsonify({
        "stats": stats,
        "recentUsers": recent_users,
        "totalUserCount": len(users),
        "adminCount": admin_count,
    })


@app.get("/api/admin/users")
@role_required("admin")
def api_admin_users():
    """Mirrors the join logic the removed admin_users_page() used to do
    — the per-user mutation endpoints below (role/enabled/delete/create)
    were already JSON and stay as-is."""
    users = _users_with_subscriptions(_cached_list_all_users())
    return jsonify({"users": users})


@app.post("/api/admin/users/<email>/role")
@role_required("admin")
def api_admin_set_user_role(email):
    data = request.get_json(silent=True) or {}
    if email == _current_user()["email"] and not data.get("admin", True):
        return jsonify({"error": "You can't remove your own admin access."}), 400
    cognito_connector.set_admin(email, bool(data.get("admin")))
    _invalidate_admin_users_cache()
    return jsonify({"ok": True})


@app.post("/api/admin/users/<email>/enabled")
@role_required("admin")
def api_admin_set_user_enabled(email):
    data = request.get_json(silent=True) or {}
    if email == _current_user()["email"] and not data.get("enabled", True):
        return jsonify({"error": "You can't disable your own account."}), 400
    cognito_connector.set_enabled(email, bool(data.get("enabled")))
    _invalidate_admin_users_cache()
    return jsonify({"ok": True})


@app.post("/api/admin/users/<email>/delete")
@role_required("admin")
def api_admin_delete_user(email):
    if email == _current_user()["email"]:
        return jsonify({"error": "You can't delete your own account."}), 400
    try:
        cognito_connector.delete_user(email)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    _invalidate_admin_users_cache()
    return jsonify({"ok": True})


def _generate_temp_password():
    rand = random.SystemRandom()
    upper = rand.choice(string.ascii_uppercase)
    digit = rand.choice(string.digits)
    rest = "".join(rand.choices(string.ascii_letters + string.digits, k=8))
    return upper + digit + rest


@app.post("/api/admin/users")
@role_required("admin")
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    password = data.get("password") or _generate_temp_password()
    make_admin = bool(data.get("makeAdmin"))

    if not email or not name:
        return jsonify({"error": "Name and email are required."}), 400

    try:
        cognito_connector.admin_create_user(email, name, password, make_admin=make_admin)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    _invalidate_admin_users_cache()
    return jsonify({"ok": True, "email": email, "password": password})


EXPORT_LINK_TTL_SECONDS = 60


def _sign_export_token(email):
    # HMAC over email+expiry using the existing Flask secret key — no new
    # secret needed. Short TTL because this is a bearer-equivalent
    # credential embedded in a URL (visible in browser history/logs),
    # unlike the Authorization header every other endpoint uses.
    expires_at = int(time.time()) + EXPORT_LINK_TTL_SECONDS
    payload = f"{email}:{expires_at}"
    signature = hmac.new(app.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def _verify_export_token(email, token):
    try:
        expires_at_str, signature = token.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False
    if time.time() >= expires_at:
        return False
    payload = f"{email}:{expires_at}"
    expected = hmac.new(app.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/api/admin/users/export-link")
@role_required("admin")
def api_admin_users_export_link():
    """Issues a short-lived signed URL for the CSV download below — a
    plain browser navigation (window.location = url, or a real <a href>
    the browser follows) can't carry the SPA's Authorization: Bearer
    header the way a fetch() call can, so this endpoint (itself normally
    bearer-authenticated) hands back a URL that carries its own
    time-boxed credential instead."""
    user = _current_user()
    token = _sign_export_token(user["email"])
    # quote(..., safe="") — a "+" in the local part (common in test/alias
    # emails) is otherwise decoded back as a space by query-string parsing,
    # which would silently break _verify_export_token's HMAC comparison.
    email_qs = urllib.parse.quote(user["email"], safe="")
    return jsonify({"downloadUrl": f"/admin/users/export.csv?email={email_qs}&token={token}"})


@app.get("/admin/users/export.csv")
def admin_users_export_csv():
    email = request.args.get("email", "")
    token = request.args.get("token", "")
    if not (email and token and _verify_export_token(email, token)):
        user = _current_user()
        if user is None:
            abort(401)
        if user["role"] != "admin":
            abort(403)

    users = _users_with_subscriptions(_cached_list_all_users())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Email", "Name", "Role", "Confirmed", "Plan", "Subscription Status", "Joined"])
    for u in users:
        writer.writerow([
            # created_at comes back as an ISO string here (see
            # _users_with_subscriptions), not the raw datetime
            # list_all_users() itself returns — just take the date part.
            u["email"], u["name"], u["role"], u["confirmed"], u["plan"], u["sub_status"],
            u["created_at"][:10],
        ])
    response = app.response_class(buf.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=quantile-users.csv"
    return response


@app.get("/api/admin/subscriptions")
@role_required("admin")
def api_admin_subscriptions():
    return jsonify(_json_safe({"subscriptions": subscription_connector.list_all_subscriptions()}))


# Admin "Quantile Orders" page: every quantile-order-intents row merged
# with its live Dhan super order (entry leg + STOP_LOSS_LEG/TARGET_LEG)
# and its actual fills from Dhan's trade book / trade history.
_DHAN_ENTRY_OPEN_STATUSES = {"TRANSIT", "PENDING", "PART_TRADED"}
_DHAN_DEAD_STATES = {"rejected", "cancelled", "expired"}
_OUTCOME_REASONS = {"STOP_LOSS_HIT": "SL", "TARGET_HIT": "Target", "EXIT_CANCELLED": "Cancelled"}
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f else None


def _trade_time(trade):
    # Trade book says "2026-09-24 09:27:10", trade history "2026-09-24T09:27:10".
    return str(trade.get("exchangeTime") or "").replace("T", " ")


def _weighted_avg(parts):
    qty = sum(q for q, _ in parts)
    return round(sum(q * p for q, p in parts) / qty, 2) if qty else None


def _order_fills(trades, order_id, security_id, qty):
    """Real average entry/exit prices from executed trades. The entry
    fills carry the super order's own orderId, but the SL/target exit
    fills don't (confirmed live, SHYAMMETL 2026-09-24: entry under
    34326092413573, exit under 311260924226507) — so exits are matched
    as opposite-side fills of the same security after the entry, taken
    in time order up to the entry quantity. None if nothing matched."""
    entries = [t for t in trades if str(t.get("orderId")) == order_id]
    if not entries:
        return None
    side = (entries[0].get("transactionType") or "").upper()
    entry_parts = [(_num(t.get("tradedQuantity")) or 0, _num(t.get("tradedPrice")) or 0) for t in entries]
    entry_qty = qty or sum(q for q, _ in entry_parts)
    start = min(_trade_time(t) for t in entries)
    exits = sorted(
        (t for t in trades
         if str(t.get("securityId")) == str(security_id)
         and (t.get("transactionType") or "").upper() not in ("", side)
         and _trade_time(t) >= start),
        key=_trade_time,
    )
    exit_parts, got, exit_time = [], 0, None
    for t in exits:
        if got >= entry_qty:
            break
        q = min(_num(t.get("tradedQuantity")) or 0, entry_qty - got)
        exit_parts.append((q, _num(t.get("tradedPrice")) or 0))
        got += q
        exit_time = _trade_time(t)
    fully_exited = got >= entry_qty
    return {
        "entry_price": _weighted_avg(entry_parts),
        "exit_price": _weighted_avg(exit_parts) if fully_exited else None,
        "exit_time": exit_time if fully_exited else None,
    }


def _apply_fills(snap, fills, original_sl):
    if fills and fills["entry_price"]:
        snap["entry_price"] = fills["entry_price"]
    if fills and snap["state"] == "closed" and fills["exit_price"]:
        snap.update(exit_price=fills["exit_price"], exit_time=fills["exit_time"], exit_from_fills=True)
    # An SL exit at least one trailing jump beyond the original stop means
    # the stop had been trailed — judged on the real fill, not the leg
    # price. A full jump, not any gap: an untrailed stop routinely fills a
    # few paise past its trigger (AEROFLEX 2026-09-23: SL 529.65, filled
    # 530.15 — a loss, not a trail).
    if snap.get("close_reason") == "SL" and original_sl is not None and snap.get("exit_price") is not None:
        margin = snap.get("trailing_jump") or 0.01
        buy = snap.get("side", "BUY") == "BUY"
        if (snap["exit_price"] >= original_sl + margin) if buy else (snap["exit_price"] <= original_sl - margin):
            snap["close_reason"] = "Trailing SL"
    return snap


def _intent_trade_date(intent):
    # created_at is naive UTC (datetime.utcnow()); Dhan's trade dates are IST.
    try:
        created = datetime.datetime.fromisoformat(intent["created_at"]).replace(tzinfo=datetime.timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    return created.astimezone(_IST).strftime("%Y-%m-%d")


def _super_order_snapshot(order, original_sl):
    """Normalises one Dhan super order into the fields the admin page
    shows. Close reason comes from whichever exit leg actually traded.
    exit_price here is only the leg's trigger level — _apply_fills()
    replaces it with the real fill price when the trades are available."""
    side = (order.get("transactionType") or "BUY").upper()
    legs = {(l.get("legName") or "").upper(): l for l in order.get("legDetails") or [] if isinstance(l, dict)}
    sl_leg = legs.get("STOP_LOSS_LEG", {})
    target_leg = legs.get("TARGET_LEG", {})
    entry_status = (order.get("orderStatus") or "").upper()

    snap = {
        "order_id": str(order.get("orderId")),
        "dhan_status": entry_status,
        "side": side,
        "qty": _num(order.get("filledQty")) or _num(order.get("quantity")),
        "entry_price": _num(order.get("averageTradedPrice")) or _num(order.get("price")),
        "current_sl": _num(sl_leg.get("price")),
        "trailing_jump": _num(sl_leg.get("trailingJump")),
        "target_price": _num(target_leg.get("price")),
        "ltp": _num(order.get("ltp")),
        "exit_price": None,
        "close_reason": None,
        "state": "active",
        "error": None,
        "updated_at": order.get("updateTime") or order.get("createTime"),
    }

    if entry_status in _DHAN_ENTRY_OPEN_STATUSES:
        snap["state"] = "entry_pending"
    elif entry_status in ("REJECTED", "CANCELLED", "EXPIRED") and not _num(order.get("filledQty")):
        snap["state"] = entry_status.lower()
        # omsErrorDescription is also set on success ("TRADE CONFIRMED"),
        # so only surface it when the order actually died.
        snap["error"] = order.get("omsErrorDescription") or None
    elif (target_leg.get("orderStatus") or "").upper() == "TRADED":
        snap.update(state="closed", close_reason="Target", exit_price=snap["target_price"])
    elif (sl_leg.get("orderStatus") or "").upper() == "TRADED":
        snap.update(state="closed", close_reason="SL", exit_price=snap["current_sl"])
    elif entry_status in ("CLOSED", "CANCELLED", "EXPIRED"):
        # Exited without either leg reporting TRADED (e.g. manual square-off
        # or auto square-off at 3:15) — closed, reason unknown from Dhan.
        snap.update(state="closed", close_reason="Exited")
    return snap


def _match_auto_order(intent, dhan_orders):
    """orderId of the super order trading-bot-algo placed for this intent,
    found by security + time. Needed because the bot only writes order_id
    back to the intent AFTER the trade closes (its execute_trade() blocks
    monitoring until exit), so for the whole life of an open trade the
    intent has none. Only orders the bot tagged "<SYMBOL>_AUTO" count, so
    a manual trade in the same stock is never picked up; among several
    (e.g. RMS-rejected retries) a live one beats a rejected one, then the
    newest wins."""
    try:
        created_ist = datetime.datetime.fromisoformat(intent["created_at"]).replace(tzinfo=datetime.timezone.utc).astimezone(_IST)
    except (KeyError, TypeError, ValueError):
        return ""
    since = (created_ist - datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    candidates = [
        o for o in dhan_orders.values()
        if str(o.get("securityId")) == str(intent.get("security_id"))
        and (o.get("correlationId") or "").upper().endswith("_AUTO")
        and (o.get("createTime") or "") >= since
    ]
    if not candidates:
        return ""
    best = max(candidates, key=lambda o: ((o.get("orderStatus") or "").upper() not in ("REJECTED", "CANCELLED"), o.get("createTime") or ""))
    return str(best.get("orderId"))


def _quantile_order_row(intent, dhan_orders, trades_for_date):
    original_sl = _num(intent.get("sl_price"))
    order_id = str(intent.get("order_id") or "")
    status = intent.get("status")
    stored = _json_safe(intent.get("dhan_snapshot") or {})
    snap = None

    if not order_id:
        # Open trade the bot hasn't reported yet — or one seen earlier
        # today whose order_id only lives in our saved snapshot so far.
        order_id = _match_auto_order(intent, dhan_orders) or str(stored.get("order_id") or "")

    if order_id and order_id in dhan_orders:
        snap = _super_order_snapshot(dhan_orders[order_id], original_sl)
    elif stored:
        # Not in today's Dhan order book any more — last seen state.
        snap = dict(stored)
    elif status == "closed" and order_id:
        # Closed on a past day before any snapshot was saved — rebuild
        # what we can from the intent, and the fills from trade history.
        snap = {"order_id": order_id, "state": "closed", "side": (intent.get("side") or "BUY").upper(), "qty": _num(intent.get("filled_qty")),
                "trailing_jump": _num(intent.get("trailing_jump")), "close_reason": _OUTCOME_REASONS.get(intent.get("outcome"))}

    # Real fill prices: always for an open trade (entry avg), and for a
    # closed one until its exit has been resolved from fills once — after
    # that the saved snapshot already has it, no more trade lookups.
    if snap and (snap.get("state") == "active" or (snap.get("state") == "closed" and not snap.get("exit_from_fills"))):
        trade_date = _intent_trade_date(intent)
        trades = trades_for_date(trade_date) if trade_date else []
        snap = _apply_fills(snap, _order_fills(trades, order_id, intent.get("security_id"), snap.get("qty")), original_sl)

    if snap and snap != stored:
        try:
            order_intent_connector.save_dhan_snapshot(
                intent["entry_id"], {k: (decimal.Decimal(str(v)) if isinstance(v, float) else v) for k, v in snap.items()}
            )
        except Exception:
            app.logger.exception("couldn't save dhan snapshot for %s", intent["entry_id"])

    row = {
        "entry_id": intent["entry_id"],
        "symbol": intent.get("symbol"),
        "created_at": intent.get("created_at"),
        "intent_status": status,
        "order_id": order_id or None,
        "side": intent.get("side") or "BUY",
        "original_sl": original_sl,
        "qty": _num(intent.get("filled_qty")),
        "entry_price": _num(intent.get("entry_price")),
        "current_sl": original_sl,
        "trailing_jump": _num(intent.get("trailing_jump")),
        "target_price": _num(intent.get("target_price")),
        "ltp": None,
        "exit_price": None,
        "exit_time": None,
        "close_reason": _OUTCOME_REASONS.get(intent.get("outcome")),
        "state": {"pending": "queued", "claimed": "placing", "live_filled": "active", "failed": "failed", "paper_filled": "paper"}.get(status, "closed" if status == "closed" else "unknown"),
        "dhan_status": None,
        "error": None,
    }
    if snap:
        row.update({k: v for k, v in snap.items() if v is not None})
        if row["state"] not in _DHAN_DEAD_STATES:
            row["error"] = None  # older snapshots saved "TRADE CONFIRMED" here
    if row["state"] in ("queued", "placing") and _intent_trade_date(intent) != datetime.datetime.now(_IST).strftime("%Y-%m-%d"):
        # Still pending/claimed from a past day — trading-bot-algo never
        # wrote a result back, so don't show it as in progress.
        row["state"] = "no_result"
    return row


def _quantile_order_pnl(row):
    exit_or_ltp = row["exit_price"] if row["state"] == "closed" else row["ltp"]
    if row["entry_price"] is None or exit_or_ltp is None or not row["qty"]:
        return None
    per_share = exit_or_ltp - row["entry_price"]
    if row["side"] == "SELL":
        per_share = -per_share
    return round(per_share * row["qty"], 2)


@app.get("/api/admin/quantile-orders")
@role_required("admin")
def api_admin_quantile_orders():
    intents = order_intent_connector.list_all_intents()
    dhan_error = None
    dhan_orders = {}
    # Also for "claimed" intents: an open trade has no order_id on the
    # intent yet, and is matched against the order book instead.
    if any((i.get("order_id") or i.get("status") == "claimed") and i.get("status") != "paper_filled" for i in intents):
        try:
            dhan_orders = dhan_connector.get_super_orders()
        except Exception as exc:
            app.logger.exception("Dhan super order book fetch failed")
            dhan_error = str(exc)

    trades_by_date = {}
    trade_book = []

    def trades_for_date(date_str):
        # Fetched lazily, at most once per date per request. The trade
        # book is checked first for every date, not only today: it keeps
        # the last session's trades until Dhan resets it next morning,
        # while trade history lags by a day or more (confirmed live
        # 2026-09-25: history for the 24th was still empty, the book had
        # all its fills). Not merged — history reports exchangeTradeId
        # "0", so the same fill can't be deduplicated across the two.
        if date_str not in trades_by_date:
            if not trade_book:
                try:
                    trade_book.extend(dhan_connector.get_trade_book())
                except Exception:
                    app.logger.exception("Dhan trade book fetch failed")
            trades = [t for t in trade_book if _trade_time(t).startswith(date_str)]
            if not trades:
                try:
                    trades = dhan_connector.get_trade_history(date_str)
                except Exception:
                    app.logger.exception("Dhan trade history fetch failed for %s", date_str)
            trades_by_date[date_str] = trades
        return trades_by_date[date_str]

    rows = []
    for intent in intents:
        row = _quantile_order_row(intent, dhan_orders, trades_for_date)
        # The order book's ltp is frozen at order time — use a live quote
        # for trades still open.
        if row["state"] == "active" and intent.get("security_id"):
            row["ltp"] = dhan_connector.get_circuit_limits(intent["security_id"], max_attempts=1)[0] or row["ltp"]
        row["pnl"] = _quantile_order_pnl(row)
        rows.append(row)
    return jsonify({"orders": rows, "dhan_error": dhan_error})


@app.get("/api/admin/campaigns")
@role_required("admin")
def api_admin_campaigns_bootstrap():
    return jsonify(_json_safe({"campaigns": subscription_connector.list_campaigns(), "plans": subscription_connector.PLANS}))


@app.post("/api/admin/campaigns")
@role_required("admin")
def api_admin_create_campaign():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    try:
        campaign = subscription_connector.create_campaign(
            name=data.get("name"),
            code=data.get("code"),
            percent_off=data.get("percentOff"),
            applicable_plans=data.get("applicablePlans"),
            active=data.get("active", True),
            visible=data.get("visible", True),
            max_redemptions=data.get("maxRedemptions") or None,
            created_by=user["email"],
        )
    except subscription_connector.SubscriptionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "campaign": campaign})


@app.post("/api/admin/campaigns/<code>/update")
@role_required("admin")
def api_admin_update_campaign(code):
    data = request.get_json(silent=True) or {}
    fields = {k: v for k, v in data.items() if k in ("active", "visible")}
    try:
        campaign = subscription_connector.update_campaign(code, **fields)
    except subscription_connector.SubscriptionError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "campaign": campaign})


@app.post("/api/admin/campaigns/<code>/delete")
@role_required("admin")
def api_admin_delete_campaign(code):
    subscription_connector.delete_campaign(code)
    return jsonify({"ok": True})


@app.get("/api/admin/scanner-campaign/bootstrap")
@role_required("admin")
def api_admin_scanner_campaign_bootstrap():
    """Everything admin_scanner_campaign_page() gathers on GET, MINUS the
    default-template auto-seed — that's now an explicit action (see
    api_admin_seed_default_template below), not a side effect of loading
    the page. Scanner results themselves aren't included here — the SPA
    calls the same GET /api/scanners + /api/scanners/<id>/cached the
    Scanner page already uses, rather than duplicating that data shape."""
    return jsonify({
        "entries": [_entry_json_safe(e) for e in campaign_connector.list_entries()],
        "notifications": campaign_connector.list_recent_notifications(),
        "templates": campaign_connector.list_templates(),
        "pushConfigured": fcm_connector.is_configured(),
        "pushTokenCount": len(campaign_connector.list_all_push_tokens()),
    })


@app.post("/api/admin/scanner-campaign/seed-default-template")
@role_required("admin")
def api_admin_seed_default_template():
    """Explicit version of the side-effecting write admin_scanner_
    campaign_page() used to do implicitly on every GET when no templates
    existed yet — the SPA calls this once, deliberately, if the
    bootstrap response comes back with an empty templates list."""
    if campaign_connector.list_templates():
        return jsonify({"error": "Templates already exist."}), 400
    template = campaign_connector.create_template(
        name="Default",
        title="",
        header="",
        entry_line_template="{{symbol}} — Entry {{entry}}, SL {{sl}}, Target {{target}}",
        footer="⚠️ This is for educational purposes only. Not a buy/sell recommendation. Trade at your own risk.",
        created_by="system",
    )
    return jsonify({"ok": True, "template": template})


@app.post("/api/admin/campaign-entries")
@role_required("admin")
def api_admin_create_entry():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    try:
        entry = campaign_connector.create_entry(
            symbol=data.get("symbol"),
            entry_price=data.get("entryPrice"),
            sl_price=data.get("slPrice"),
            target_price=data.get("targetPrice"),
            note=data.get("note"),
            source=data.get("source") or "manual",
            entry_type=data.get("type"),
            created_by=user["email"],
        )
    except campaign_connector.CampaignError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "entry": _entry_json_safe(entry)})


# Alternative "instant" qualification (added 2026-09-21) for a stock
# whose 2nd candle never pulls back at all — it just keeps running. The
# original pullback rule alone missed these entirely. A stock qualifies
# this way when its FIRST candle already closed within this fraction of
# its own high-low range, measured down from the high — e.g. 0.20 means
# the close sits in the top 20% of the candle's range, so barely any
# upper shadow: strong enough that a 2nd-candle pullback isn't needed to
# call it a real setup. Same entry (1st candle high) and SL (2nd candle
# low) either way — this only changes which stocks qualify, not the
# trade levels themselves.
INSTANT_QUALIFY_NEAR_HIGH_FRACTION = 0.20

# Stop-loss sits a little below the 2nd candle's low rather than exactly
# on it, so a wick that just tags the low doesn't stop the trade out.
SL_BUFFER_PCT = 0.30
# NSE tick size: 0.05 for most stocks, 0.01 for some low-priced ones — a
# multiple of 0.05 is valid under both, and Dhan rejects off-tick prices.
PRICE_TICK = 0.05


def _buffered_sl(candle_low):
    """candle_low minus SL_BUFFER_PCT, rounded DOWN to PRICE_TICK (down,
    so rounding only ever widens the buffer, never shrinks it)."""
    raw = candle_low * (1 - SL_BUFFER_PCT / 100)
    return round(math.floor(round(raw / PRICE_TICK, 6)) * PRICE_TICK, 2)


def _create_breakout_entries_for_symbols(symbols, created_by):
    """Shared by the admin's manual "+ Breakout alert" action (api_admin_
    create_breakout_entries below) and the automatic morning bot
    (_auto_create_breakout_alerts) — entry = the first opening candle's
    high, stop-loss = the second candle's low, either way. A stock
    qualifies via EITHER of two conditions (see INSTANT_QUALIFY_NEAR_
    HIGH_FRACTION above for the second one):
      1. Pullback: the second candle closed red.
      2. Instant: the second candle didn't pull back, but the FIRST
         candle already closed near its own high (no pullback needed —
         the stock was already strong enough on the opening candle
         alone).
    Each entry created then gets tracked exactly like any other (see the
    alert-tracking bot below) — covering many stocks at once means each
    is notified independently the moment its own entry/SL is hit, same
    as any other campaign entry. Returns a list of {symbol, ok, ...} —
    never raises for an individual symbol."""
    today = datetime.datetime.now(chart_connector.IST).strftime("%Y-%m-%d")
    resolved, _unresolved = dhan_connector.resolve_security_ids(symbols)

    results = []
    for symbol in symbols:
        security_id = resolved.get(symbol)
        if security_id is None:
            results.append({"symbol": symbol, "ok": False, "reason": "Symbol not found."})
            continue

        # Checked before candle shape, using Dhan's own live circuit
        # data rather than inferring it from a frozen candle — a stock
        # can be near (not just exactly at) its circuit while still
        # producing candles that would otherwise pass the pullback/
        # instant-qualify checks below. Rejecting here means it never
        # even becomes a "New watch" alert, not just a blocked order
        # later (confirmed live: TBZ, 2026-09-22). Also excludes any
        # 5%-circuit-band stock outright, regardless of current price
        # proximity — 5% bands never get scanned at all, per request.
        circuit_reason = dhan_connector.circuit_reject_reason(security_id)
        if circuit_reason:
            results.append({"symbol": symbol, "ok": False, "reason": circuit_reason})
            continue

        try:
            move = dhan_connector.get_opening_move(security_id, today, interval=first_minute_mod.INTERVAL_MINUTES)
        except Exception as exc:
            results.append({"symbol": symbol, "ok": False, "reason": str(exc)})
            continue

        first_candle, second_candle = move["first_candle"], move["second_candle"]
        if first_candle is None:
            results.append({"symbol": symbol, "ok": False, "reason": "First candle hasn't formed yet."})
            continue
        if second_candle is None:
            results.append({"symbol": symbol, "ok": False, "reason": f"Second candle hasn't formed yet - try again after the {first_minute_mod.INTERVAL_MINUTES * 2}-minute mark."})
            continue

        pulled_back = second_candle["close"] < second_candle["open"]
        candle_range = first_candle["high"] - first_candle["low"]
        closed_near_high = candle_range > 0 and (first_candle["high"] - first_candle["close"]) <= INSTANT_QUALIFY_NEAR_HIGH_FRACTION * candle_range

        if not (pulled_back or closed_near_high):
            results.append({"symbol": symbol, "ok": False, "reason": "Second candle isn't red and the first candle didn't close near its high - no qualifying setup."})
            continue

        qualify_reason = "pullback candle" if pulled_back else "1st candle closed near its high, no pullback needed"

        entry_price = first_candle["high"]
        second_low = second_candle["low"]

        # A stock that hits its own circuit (5%/10%/20% band) right at
        # open freezes there for the rest of the session — every candle
        # after the freeze prints open=high=low=close at the locked
        # price. Confirmed live (TBZ, 2026-09-22): that produces a 2nd
        # candle low equal to the 1st candle's high, so entry_price ==
        # sl_price exactly — a zero-risk-distance "setup" that isn't a
        # real breakout at all, just a data artifact. Left unguarded,
        # its SL% is unbeatably 0%, so the race's lowest-SL%-wins rule
        # picks it over every legitimate qualifier every time (it did:
        # RPTECH/UNIMECH/ROSSTECH all lost to it that morning). Checked
        # on the raw low, BEFORE the SL buffer — buffering first would
        # push a frozen candle's SL just under its entry and let it pass.
        if second_low >= entry_price:
            results.append({"symbol": symbol, "ok": False, "reason": f"2nd candle low ({second_low}) isn't below entry ({entry_price}) — likely a circuit-frozen candle, not a real breakout setup."})
            continue
        sl_price = _buffered_sl(second_low)
        try:
            entry = campaign_connector.create_entry(
                symbol=symbol,
                entry_price=entry_price,
                sl_price=sl_price,
                target_price=None,
                note=(
                    f"Breakout setup ({qualify_reason}): {first_minute_mod.INTERVAL_MINUTES}-min opening "
                    f"candle high {entry_price:.2f} (entry), SL {sl_price:.2f} "
                    f"(2nd candle low {second_low:.2f} - {SL_BUFFER_PCT:.2f}%)"
                ),
                source="first_minute_movers",
                entry_type="momentum",
                created_by=created_by,
            )
        except campaign_connector.CampaignError as exc:
            results.append({"symbol": symbol, "ok": False, "reason": str(exc)})
            continue

        # Being added here is itself news — until now, a subscriber heard
        # NOTHING about this stock until (and unless) price later actually
        # crossed entry_price, minutes or hours after the setup was
        # identified. This complements, not replaces, the alert-tracking
        # bot's own "entry_triggered" notification below — one says
        # "watch this," the other says "it just happened."
        try:
            _send_campaign_notification(
                f"👀 New watch — {symbol}",
                f"{symbol} qualified for a breakout setup ({qualify_reason}): watch for a break above ₹{entry_price:.2f} (SL ₹{sl_price:.2f}).",
                ALERT_MONITOR_AUDIENCE,
                entry_symbols=[symbol],
                channels=("in_app", "push") if fcm_connector.is_configured() else ("in_app",),
                sent_by=created_by,
            )
        except Exception as exc:
            print(f"[breakout-entries] new-watch notify failed for {symbol}: {exc}", file=sys.stderr)

        results.append({"symbol": symbol, "ok": True, "entryPrice": entry_price, "slPrice": sl_price, "entry": entry})

    return results


@app.post("/api/admin/scanner-campaign/breakout-entries")
@role_required("admin")
def api_admin_create_breakout_entries():
    """Batch-creates campaign entries for a set of stocks the admin picked
    by hand from the First-Minute Gainers/Losers scanner's rows — see
    _create_breakout_entries_for_symbols for the actual rule. AUTO_
    BREAKOUT_ENABLED's automatic version (below) covers "just do this for
    me every morning" instead."""
    user = _current_user()
    data = request.get_json(silent=True) or {}
    symbols = sorted({(s or "").strip().upper() for s in (data.get("symbols") or []) if (s or "").strip()})
    if not symbols:
        return jsonify({"error": "Select at least one stock."}), 400

    results = _create_breakout_entries_for_symbols(symbols, created_by=user["email"])
    for r in results:
        if r.get("ok"):
            r["entry"] = _entry_json_safe(r["entry"])
    return jsonify({"results": results})


@app.post("/api/admin/campaign-entries/<entry_id>/update")
@role_required("admin")
def api_admin_update_entry(entry_id):
    data = request.get_json(silent=True) or {}
    fields = {}
    for key, field in [("entryPrice", "entry_price"), ("slPrice", "sl_price"), ("targetPrice", "target_price"), ("note", "note"), ("active", "active"), ("type", "type")]:
        if key in data:
            fields[field] = data[key]
    try:
        entry = campaign_connector.update_entry(entry_id, **fields)
    except campaign_connector.CampaignError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "entry": _entry_json_safe(entry)})


@app.post("/api/admin/campaign-entries/<entry_id>/delete")
@role_required("admin")
def api_admin_delete_entry(entry_id):
    campaign_connector.delete_entry(entry_id)
    return jsonify({"ok": True})


@app.post("/api/admin/campaign/ai-generate")
@role_required("admin")
def api_admin_campaign_ai_generate():
    data = request.get_json(silent=True) or {}
    instruction = (data.get("instruction") or "").strip()
    entries = data.get("entries") or []
    try:
        copy = campaign_ai.generate_campaign_copy(
            instruction=instruction,
            entries=entries,
            market_status=_market_status(),
            today=datetime.datetime.now(chart_connector.IST).strftime("%A, %d %b %Y"),
        )
    except Exception as exc:
        return jsonify({"error": f"AI generation failed: {exc}"}), 502
    return jsonify({"ok": True, "title": copy["title"], "header": copy["header"], "entryLineTemplate": copy["entry_line_template"]})


@app.get("/api/admin/campaign/ai-screen")
@role_required("admin")
def api_admin_campaign_ai_screen():
    """Screens today's EMA 10/20 Breakout matches for a consolidation-
    breakout-on-volume setup with a bullish EMA stack, down to a top 5 —
    see connectors/stock_screener_ai.py. The candidate pool is always
    this one scanner (not admin-selectable) — it's the only one of the
    two scanners that actually gives every candidate a today's-High/Low/
    Price to screen with in the first place."""
    entry = cache.peek(_scanner_cache_key("dhan_ema_breakout"))
    if not entry or not entry["data"].get("rows"):
        return jsonify({"error": "Run the EMA 10/20 Breakout scanner first so there are matches to screen."}), 400

    rows = entry["data"]["rows"]
    columns = entry["data"].get("columns", [])
    symbol_key = next((c["key"] for c in columns if c.get("type") == "symbol"), None)
    if not symbol_key:
        return jsonify({"error": "Couldn't find the symbol column in the scanner result."}), 400

    symbols = []
    for row in rows:
        symbol = row.get(symbol_key)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    symbols = symbols[:50]  # keeps the Claude call reasonably sized — matches the "15-50 stocks" scope

    candidates = []
    skipped = 0
    for symbol in symbols:
        try:
            bars = chart_connector.get_ohlcv(symbol)
            metrics = stock_screener_ai.compute_candidate_metrics(symbol, bars)
        except Exception:
            metrics = None
        if metrics is None:
            skipped += 1
            continue
        candidates.append(metrics)

    if not candidates:
        return jsonify({"error": "None of today's matches had enough price history (200+ days) to screen."}), 400

    try:
        picks = stock_screener_ai.screen_top_picks(candidates)
    except Exception as exc:
        return jsonify({"error": f"AI screening failed: {exc}"}), 502

    by_symbol = {c["symbol"]: c for c in candidates}
    for pick in picks:
        c = by_symbol.get(pick["symbol"])
        if c:
            pick["high"] = c["latest_high"]
            pick["low"] = c["latest_low"]

    return jsonify({"ok": True, "picks": picks, "screened": len(candidates), "skipped": skipped})


@app.post("/api/admin/campaign-templates")
@role_required("admin")
def api_admin_create_template():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    try:
        template = campaign_connector.create_template(
            name=data.get("name"),
            title=data.get("title"),
            header=data.get("header"),
            entry_line_template=data.get("entryLineTemplate"),
            footer=data.get("footer"),
            created_by=user["email"],
        )
    except campaign_connector.CampaignError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "template": template})


@app.post("/api/admin/campaign-templates/<template_id>/delete")
@role_required("admin")
def api_admin_delete_template(template_id):
    campaign_connector.delete_template(template_id)
    return jsonify({"ok": True})


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _split_cta_for_push(body):
    """The composed body may contain a Markdown-style CTA link, e.g.
    "[View Chart](https://...)" — the campaign builder's chart-link
    convention. The in-app bell feed renders that as a real, clean
    clickable button and hides the raw URL (see _header.html's linkify()).

    Push notifications get an even better version of the same idea: a
    real native action BUTTON at the bottom of the notification (the
    Notification API's `actions`, wired up in the service worker below) —
    not just clickable body text. That means the CTA line doesn't belong
    in the visible body at all here; it's removed entirely, and its
    label + URL travel separately in FCM's `data` field (invisible,
    read by the service worker to build the actual button). Returns
    (plain_body, cta_url_or_none, cta_label_or_none)."""
    match = _MARKDOWN_LINK_RE.search(body)
    if not match:
        return body, None, None
    cta_label, cta_url = match.group(1), match.group(2)
    plain_body = _MARKDOWN_LINK_RE.sub("", body)
    plain_body = re.sub(r"\n{2,}", "\n", plain_body).strip()
    return plain_body, cta_url, cta_label


def _send_campaign_notification(title, body, audience, entry_symbols=None, channels=("in_app", "push"), sent_by="system"):
    """Shared by the admin's manual "Send to audience" action
    (api_admin_send_campaign below) and the automated alert-tracking bot
    (_check_and_notify_active_entries) — same audience filtering, same
    push CTA handling, same notification-log write, so a bot-triggered
    alert behaves identically to one an admin sent by hand. Returns
    (recipient_count, sent_push); raises RuntimeError if "push" was
    requested but Firebase isn't configured (callers that can't show the
    admin a form error, like the bot, should just drop "push" from
    channels up front instead of hitting this)."""
    all_users = cognito_connector.list_all_users()
    plans = subscription_connector.get_plans_for_emails([u["email"] for u in all_users])
    recipient_emails = [u["email"] for u in all_users if plans.get(u["email"], "free") in audience]
    recipient_count = len(recipient_emails)

    sent_push = 0
    if "push" in channels:
        if not fcm_connector.is_configured():
            raise RuntimeError("Push notifications aren't set up yet.")
        tokens = campaign_connector.list_push_tokens_for_emails(recipient_emails)
        push_body, cta_url, cta_label = _split_cta_for_push(body)
        push_data = {"url": cta_url, "cta_label": cta_label} if cta_url else None
        sent_push, stale = fcm_connector.send_to_tokens(tokens, title, push_body, data=push_data)
        for stale_token in stale:
            campaign_connector.remove_push_token(stale_token)

    if "in_app" in channels:
        campaign_connector.record_notification(
            title=title, body=body, entry_symbols=entry_symbols or [], channels=list(channels),
            recipient_count=recipient_count, sent_by=sent_by, audience=audience,
        )
    return recipient_count, sent_push


@app.post("/api/admin/campaign/send")
@role_required("admin")
def api_admin_send_campaign():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    entry_symbols = data.get("entrySymbols") or []
    channels = [c for c in (data.get("channels") or []) if c in ("in_app", "push")]
    audience = [a for a in (data.get("audience") or []) if a in ("free", "pro", "premium")]

    if not title or not body:
        return jsonify({"error": "Title and message body are required."}), 400
    if not channels:
        return jsonify({"error": "Choose at least one channel."}), 400
    if not audience:
        return jsonify({"error": "Choose at least one audience (Free/Pro/Premium)."}), 400
    if "push" in channels and not fcm_connector.is_configured():
        return jsonify({"error": "Push notifications aren't set up yet — send In-app only, or configure Firebase first."}), 503

    recipient_count, sent_push = _send_campaign_notification(
        title, body, audience, entry_symbols=entry_symbols, channels=channels, sent_by=user["email"],
    )
    return jsonify({"ok": True, "recipientCount": recipient_count, "pushSent": sent_push})


# ============================================================
# ALERT-TRACKING BOT
#
# Watches every ACTIVE campaign entry (connectors/campaign_connector.py's
# trade ideas — symbol + entry/SL/target) against its live price and
# notifies subscribers automatically, the first time each milestone is
# crossed: the entry level itself, +2% profit, a 1:1 risk-reward, and a
# 1:2 risk-reward (with a suggested trailing stop-loss at that point).
# Runs on its own background thread (see _start_alert_monitor, started
# from __main__ below) on a fixed interval during market hours — this is
# a bot, not something an admin has to trigger by hand.
#
# Assumes every entry is a long/buy setup (SL below entry, target above)
# — the same convention this whole admin campaign builder already uses
# everywhere else (auto-fill, AI screening, etc.), not a new assumption.
# ============================================================

PROFIT_MILESTONE_PCT = 2.0
ALERT_MILESTONES = ["entry_triggered", "profit_2pct", "rr_1_1", "rr_1_2", "sl_hit"]  # order matters — see _check_and_notify_active_entries
ALERT_MONITOR_AUDIENCE = ["pro", "premium"]
ALERT_MONITOR_INTERVAL_SECONDS = 5 * 60

# Automatic version of the admin's manual "+ Breakout alert" action (see
# _create_breakout_entries_for_symbols) — once each morning, takes ALL
# AUTO_BREAKOUT_TOP_N gainers from the First-Minute Gainers/Losers scanner
# (10 -> the scanner's own full gainers list, widened from an original 4
# on 2026-09-21 so a real gainer that doesn't make a tiny top-4 cut still
# gets considered) and applies the same qualification rule (pullback OR
# instant-near-high, see _create_breakout_entries_for_symbols), with no
# admin click needed. Window: the 2nd candle needs INTERVAL_MINUTES*2
# after 09:15 to have actually formed (09:25 for the current 5-min
# interval), and this only makes sense as a same-morning signal — a
# late-afternoon run using hours-old opening candles would be pointless,
# not just redundant. Called from _breakout_watch_loop (below), NOT this
# alert-monitor's own slower loop — the "does it qualify yet" retry and
# the post-qualify "has it broken out yet" race both run on the same
# fast 1-minute cadence, so a stock that only just qualifies doesn't sit
# up to 5 minutes before its first breakout check.
AUTO_BREAKOUT_ENABLED = True
AUTO_BREAKOUT_TOP_N = 10
AUTO_BREAKOUT_WINDOW_START = f"09:{15 + first_minute_mod.INTERVAL_MINUTES * 2:02d}"
AUTO_BREAKOUT_WINDOW_END = "10:30"
_auto_breakout_state = {"date": None, "done": False, "symbols": None, "resolved": set(), "executor_prewarmed": False}

# _auto_breakout_state is also saved to disk after every tick and
# restored on the first tick after a restart — otherwise a backend
# restart (deploy, EC2 stop/start) inside the window forgot the day's
# progress: it re-scanned, could lock in a different top-N, re-created
# the same "New watch" alerts, and — if a winner had already been
# picked — resumed qualifying, letting a second stock trigger a second
# order. .cache/ is git-ignored and on the instance's own disk, so it
# survives both a service restart and an instance stop/start.
AUTO_BREAKOUT_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def _auto_breakout_state_path(date_str):
    return os.path.join(AUTO_BREAKOUT_STATE_DIR, f"auto_breakout_state_{date_str}.json")


def _save_auto_breakout_state():
    state = _auto_breakout_state
    if not state["date"]:
        return
    payload = {**state, "resolved": sorted(state["resolved"])}
    path = _auto_breakout_state_path(state["date"])
    try:
        os.makedirs(AUTO_BREAKOUT_STATE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)  # atomic — a crash mid-write can't leave a half file
    except OSError as exc:
        print(f"[auto-breakout] couldn't save state: {exc}", file=sys.stderr)


def _load_auto_breakout_state(date_str):
    try:
        with open(_auto_breakout_state_path(date_str), encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return None
    if saved.get("date") != date_str:
        return None
    return {**saved, "resolved": set(saved.get("resolved") or [])}


def _todays_breakout_entries(today_str):
    """Every breakout alert created today (active or not) — the database's
    own record of what already ran, used as a backstop if the saved state
    file is ever missing (e.g. a freshly launched instance)."""
    try:
        entries = campaign_connector.list_entries()
    except Exception as exc:
        print(f"[auto-breakout] couldn't read today's entries: {exc}", file=sys.stderr)
        return []
    return [e for e in entries if e.get("source") == "first_minute_movers" and (e.get("created_at") or "").startswith(today_str)]


def _start_auto_breakout_day(today_str):
    restored = _load_auto_breakout_state(today_str)
    if restored:
        _auto_breakout_state.update(restored)
        print(f"[auto-breakout] {today_str}: resumed saved state after restart (done={restored['done']}, symbols={restored['symbols']})", file=sys.stderr)
        return
    _auto_breakout_state.update(date=today_str, done=False, symbols=None, resolved=set(), executor_prewarmed=False)
    todays = _todays_breakout_entries(today_str)
    if any("entry_triggered" in (e.get("milestones_notified") or []) for e in todays):
        # Today's race already has a winner — never qualify more stocks.
        _auto_breakout_state["done"] = True
        print(f"[auto-breakout] {today_str}: no saved state, but today's winner already triggered — nothing more to do today", file=sys.stderr)

# The dedicated-IP order-executor pipeline (trading-bot-algo polling
# quantile-order-intents) has been built and end-to-end tested against
# real infra (see 2026-09-21 verification). Enabled for tomorrow's
# real breakout to generate a real order intent — trading-bot-algo
# itself is still in PAPER_MODE (SSM /trading-bot-algo/paper_mode),
# so this produces a paper trade to review, not a real Dhan order.
AUTO_ORDER_ON_BREAKOUT_ENABLED = True


def _auto_create_breakout_alerts():
    """Runs on every breakout-watch tick (every BREAKOUT_WATCH_INTERVAL_
    SECONDS while markets are open — see _breakout_watch_loop) but only
    actually does anything within the AUTO_BREAKOUT_WINDOW_START..END
    IST window, and only once per
    calendar day overall — tracked in _auto_breakout_state, not a one-shot
    flag set after the very first attempt: the top-N gainer list is frozen
    the first tick data is available (so a shifting ranking across ticks
    can't add more than AUTO_BREAKOUT_TOP_N entries total), but each of
    those frozen symbols keeps getting retried on later ticks for as long
    as its own outcome is still "second candle hasn't formed yet" — a
    stock whose second candle is confirmed red (added), confirmed NOT red,
    or simply not found is resolved immediately and never retried, since
    none of those outcomes can change. Only once every symbol is resolved,
    or the window closes, does today's run end — a single attempt at
    09:25 that comes up empty is NOT treated as "no match for today"."""
    if not AUTO_BREAKOUT_ENABLED:
        return

    now = datetime.datetime.now(chart_connector.IST)
    today_str = now.strftime("%Y-%m-%d")
    if _auto_breakout_state["date"] != today_str:
        _start_auto_breakout_day(today_str)

    if _auto_breakout_state["done"]:
        return
    try:
        _auto_breakout_tick(now, today_str)
    finally:
        _save_auto_breakout_state()


def _auto_breakout_tick(now, today_str):
    now_hm = now.strftime("%H:%M")
    if now_hm < AUTO_BREAKOUT_WINDOW_START:
        return
    window_closed = now_hm > AUTO_BREAKOUT_WINDOW_END

    # Pre-warm the dedicated-IP order executor the moment the window
    # opens, in parallel with qualification/the race — not when a
    # winner is declared. Its cold boot (yum update, pip install, git
    # clone) has taken anywhere from ~60s to several minutes in
    # testing; waiting until a winner is known to even start booting
    # meant the instance could still be booting while the stock kept
    # moving, and place_trade() re-quotes at whatever LTP is current
    # when it finally places — so a slow boot doesn't risk the order
    # never filling, but does risk filling well away from the intended
    # entry with the same original SL, skewing the trade's real RR.
    # A stock can't realistically win before its own 2nd candle even
    # forms, a few minutes after window open at the earliest, so this
    # gives the instance a real head start. Fires at most once per day
    # (idempotent either way - trigger_order_executor's Lambda is a
    # no-op if an instance is already up) and only if auto-ordering is
    # actually enabled.
    if AUTO_ORDER_ON_BREAKOUT_ENABLED and not _auto_breakout_state["executor_prewarmed"]:
        _auto_breakout_state["executor_prewarmed"] = True
        try:
            order_intent_connector.trigger_order_executor()
            print(f"[auto-breakout] {today_str}: pre-warmed order executor at window open", file=sys.stderr)
        except Exception as exc:
            print(f"[auto-breakout] pre-warm failed: {exc}", file=sys.stderr)

    if _auto_breakout_state["symbols"] is None:
        try:
            gainers_df, _losers_df = first_minute_mod.get_first_minute_gainers_losers(top_n=AUTO_BREAKOUT_TOP_N)
        except Exception as exc:
            print(f"[auto-breakout] scan failed: {exc}", file=sys.stderr)
            if window_closed:
                _auto_breakout_state["done"] = True
                print(f"[auto-breakout] {today_str}: window closed with no successful scan - nothing added today", file=sys.stderr)
            return
        if gainers_df.empty:
            if window_closed:
                _auto_breakout_state["done"] = True
                print(f"[auto-breakout] {today_str}: window closed with no scanner data - nothing added today", file=sys.stderr)
            return
        _auto_breakout_state["symbols"] = gainers_df.head(AUTO_BREAKOUT_TOP_N)["Stock Name"].tolist()
        print(f"[auto-breakout] {today_str}: locked in top {AUTO_BREAKOUT_TOP_N} gainers {_auto_breakout_state['symbols']}", file=sys.stderr)

    pending = [s for s in _auto_breakout_state["symbols"] if s not in _auto_breakout_state["resolved"]]
    if pending:
        # Backstop against duplicates if the saved state was lost: a stock
        # that already has a breakout alert today is done, not re-created.
        already = {e.get("symbol") for e in _todays_breakout_entries(today_str)} & set(pending)
        if already:
            _auto_breakout_state["resolved"] |= already
            pending = [s for s in pending if s not in already]
            print(f"[auto-breakout] {today_str}: skipping {sorted(already)} - already have an alert today", file=sys.stderr)
    if pending:
        results = _create_breakout_entries_for_symbols(pending, created_by="auto-breakout-bot")
        for r in results:
            still_pending = not r["ok"] and "hasn't formed yet" in (r.get("reason") or "")
            if not still_pending:
                _auto_breakout_state["resolved"].add(r["symbol"])
        print(f"[auto-breakout] {today_str} attempt on {pending}: {results}", file=sys.stderr)

    if window_closed or len(_auto_breakout_state["resolved"]) >= len(_auto_breakout_state["symbols"]):
        _auto_breakout_state["done"] = True
        unresolved = set(_auto_breakout_state["symbols"]) - _auto_breakout_state["resolved"]
        if unresolved:
            print(f"[auto-breakout] {today_str}: window closed, still pending: {sorted(unresolved)}", file=sys.stderr)


def _milestones_reached(entry_price, sl_price, current_price, already_entered=False):
    """Every milestone `current_price` currently qualifies for — not just
    the newest one, since a single check can jump straight past several
    at once (e.g. a gap-up open past both the entry and 1:1 levels).

    profit_2pct/rr_1_1/rr_1_2/sl_hit only make sense once the trade has
    actually been entered. Bug fixed live 2026-09-21: sl_hit used to be
    checked purely as `current_price <= sl_price`, with no requirement
    that price had ever crossed entry_price first — a stock whose price
    fell straight through the SL level without ever rallying up to entry
    (entry_price is always above sl_price for this app's breakout-entry
    setups) got a real "Stop-loss hit" notification for a trade that was
    never actually entered (confirmed: KMEW, entry ₹3038, SL ₹2951.40,
    sl_hit notified with entry_triggered never having fired at all).
    `already_entered` (entry_triggered already notified on a prior check)
    covers the case where price crossed entry earlier and has since
    fallen back through SL; entered_now covers this same check crossing
    both at once (a real gap through both levels)."""
    reached = set()
    if entry_price is None or entry_price <= 0:
        return reached

    entered_now = current_price >= entry_price
    if entered_now:
        reached.add("entry_triggered")

    if not (already_entered or entered_now):
        return reached

    profit_pct = (current_price - entry_price) / entry_price * 100
    if profit_pct >= PROFIT_MILESTONE_PCT:
        reached.add("profit_2pct")

    if sl_price is not None:
        risk = entry_price - sl_price
        if risk > 0:
            reward = current_price - entry_price
            rr = reward / risk
            if rr >= 1.0:
                reached.add("rr_1_1")
            if rr >= 2.0:
                reached.add("rr_1_2")
        if current_price <= sl_price:
            reached.add("sl_hit")

    return reached


# Position-sizing instruction appended to the entry_triggered notification
# (below) — full size only when the broader market is actually cooperating
# (a healthy % of the tracked watchlist advancing today), half size
# otherwise, so "the tape is working against you" automatically shows up
# as a smaller suggested position instead of something a subscriber has
# to separately check market breadth and remember to apply themselves.
BREADTH_FULL_QTY_THRESHOLD_PCT = 50.0


def _market_breadth_positive_pct():
    """% of the tracked watchlist (~356 stocks) currently advancing —
    reuses the SAME cached breadth data the dashboard's own Market Breadth
    card already computes (_dashboard_watchlist_metrics / _breadth_from_
    metrics), not a separate calculation. None if that data isn't
    available yet (e.g. very first minutes after this process started,
    before the 15-min-cached metrics have been fetched once)."""
    breadth = _breadth_from_metrics(_dashboard_watchlist_metrics())
    if not breadth or not breadth["sampleSize"]:
        return None
    return breadth["advancing"] / breadth["sampleSize"] * 100


def _quantity_instruction():
    pct = _market_breadth_positive_pct()
    if pct is None:
        return "Quantity: use your own judgement (market breadth data isn't available right now)."
    if pct >= BREADTH_FULL_QTY_THRESHOLD_PCT:
        return f"Quantity: FULL — market breadth is positive ({pct:.0f}% of tracked stocks advancing)."
    return f"Quantity: HALF (~50%) — market breadth is weak ({pct:.0f}% of tracked stocks advancing)."


def _milestone_message(symbol, milestone, entry_price, sl_price, current_price):
    if milestone == "entry_triggered":
        return (
            f"🔔 Entry triggered — {symbol}",
            f"{symbol} has crossed your entry price of ₹{entry_price:.2f} (now ₹{current_price:.2f}). {_quantity_instruction()}",
        )
    if milestone == "profit_2pct":
        pct = (current_price - entry_price) / entry_price * 100
        return (
            f"📈 {symbol} up {pct:.1f}% from entry",
            f"{symbol} is now ₹{current_price:.2f}, {pct:+.1f}% from your entry of ₹{entry_price:.2f}.",
        )
    if milestone == "rr_1_1":
        return (
            f"✅ {symbol} hit 1:1 target",
            f"{symbol} reached ₹{current_price:.2f} — a full 1:1 risk-reward. Consider trailing your stop-loss up to breakeven (₹{entry_price:.2f}) to protect the trade.",
        )
    if milestone == "rr_1_2":
        trail_to = (entry_price + (entry_price - sl_price)) if sl_price is not None else entry_price
        return (
            f"🚀 {symbol} hit 1:2 target",
            f"{symbol} reached ₹{current_price:.2f} — a 1:2 risk-reward. Consider trailing your stop-loss up to ₹{trail_to:.2f} (your 1:1 level) to lock in profit.",
        )
    if milestone == "sl_hit":
        return (
            f"⛔ Stop-loss hit — {symbol}",
            f"{symbol} has hit your stop-loss of ₹{sl_price:.2f} (now ₹{current_price:.2f}). Consider exiting to protect capital.",
        )
    return None, None


def _entry_tracker_state(entry):
    """Live-computed milestone status for one entry — used by the "seen
    now" milestone set AND the admin UI tracker (api_admin_campaign_tracker),
    so both always agree on what "reached" means."""
    entry_price = float(entry["entry_price"]) if entry.get("entry_price") is not None else None
    sl_price = float(entry["sl_price"]) if entry.get("sl_price") is not None else None
    target_price = float(entry["target_price"]) if entry.get("target_price") is not None else None

    try:
        current_price = _symbol_change_pct(entry["symbol"])
        current_price = current_price["value"] if current_price else None
    except Exception:
        current_price = None

    already_entered = "entry_triggered" in (entry.get("milestones_notified") or [])
    reached = _milestones_reached(entry_price, sl_price, current_price, already_entered=already_entered) if (entry_price and current_price) else set()
    profit_pct = ((current_price - entry_price) / entry_price * 100) if (entry_price and current_price) else None

    return {
        "id": entry["id"],
        "symbol": entry["symbol"],
        "entryPrice": entry_price,
        "slPrice": sl_price,
        "targetPrice": target_price,
        "currentPrice": current_price,
        "profitPct": profit_pct,
        "milestonesReached": [m for m in ALERT_MILESTONES if m in reached],
        "milestonesNotified": entry.get("milestones_notified") or [],
    }


def _check_and_notify_active_entries():
    entries = campaign_connector.list_entries(active_only=True)
    for entry in entries:
        entry_price = entry.get("entry_price")
        if entry_price is None:
            continue
        entry_price = float(entry_price)
        sl_price = float(entry["sl_price"]) if entry.get("sl_price") is not None else None

        try:
            change = _symbol_change_pct(entry["symbol"])
        except Exception:
            change = None
        if not change:
            continue
        current_price = change["value"]

        already_notified = set(entry.get("milestones_notified") or [])
        reached = _milestones_reached(entry_price, sl_price, current_price, already_entered="entry_triggered" in already_notified)
        new_milestones = [m for m in ALERT_MILESTONES if m in reached and m not in already_notified]
        if not new_milestones:
            continue

        for milestone in new_milestones:
            title, body = _milestone_message(entry["symbol"], milestone, entry_price, sl_price, current_price)
            if not title:
                continue
            try:
                _send_campaign_notification(
                    title, body, ALERT_MONITOR_AUDIENCE, entry_symbols=[entry["symbol"]],
                    channels=("in_app", "push") if fcm_connector.is_configured() else ("in_app",),
                    sent_by="alert-bot",
                )
            except Exception as exc:
                print(f"[alert-monitor] notify failed for {entry['symbol']} ({milestone}): {exc}", file=sys.stderr)

        try:
            campaign_connector.update_entry(entry["id"], milestones_notified=list(already_notified | set(new_milestones)))
        except Exception as exc:
            print(f"[alert-monitor] couldn't persist milestones for {entry['symbol']}: {exc}", file=sys.stderr)


def _alert_monitor_loop():
    while True:
        try:
            if _market_status().startswith("Markets open"):
                _check_and_notify_active_entries()
        except Exception as exc:
            print(f"[alert-monitor] check cycle failed: {exc}", file=sys.stderr)
        time.sleep(ALERT_MONITOR_INTERVAL_SECONDS)


def _start_alert_monitor():
    threading.Thread(target=_alert_monitor_loop, daemon=True, name="alert-monitor").start()


# ============================================================
# BREAKOUT-WATCH BOT
#
# A second, faster, narrower bot than the general alert-monitor above,
# covering the whole breakout-batch pipeline end to end on one fast
# (BREAKOUT_WATCH_INTERVAL_SECONDS = 60s) cadence:
#   1. _auto_create_breakout_alerts() — does today's frozen top-N gainer
#      pick qualify yet (2nd candle closed red)? Retried here, not on the
#      general bot's slower 5-minute tick, so a stock isn't sitting
#      un-checked for up to 5 minutes after its 2nd candle actually closes.
#   2. _breakout_watch_once() — for whichever of those have already
#      qualified (source == "first_minute_movers", still pending
#      entry_triggered), has price crossed the entry yet? The general bot
#      would still eventually catch entry_triggered too, just up to 5
#      minutes later — this exists to react faster, and to implement
#      "first one wins": the moment ANY pending breakout-batch stock
#      actually crosses its entry price, every OTHER still-pending one
#      from that same batch is deactivated immediately, AND step 1's
#      qualification process is stopped for the rest of the day too — a
#      stock still waiting on 2nd-candle data at that exact moment can't
#      qualify a minute later and become a brand-new solo watch with
#      nothing left to race against. One-trade-from-the-batch, full
#      stop, not "notify everything that eventually triggers."
# Once a stock's entry_triggered fires here, the general bot's own
# 5-minute cadence takes over for its profit/RR/SL milestones — those
# don't need the fast loop's responsiveness.
# ============================================================

BREAKOUT_WATCH_INTERVAL_SECONDS = 60


def _breakout_watch_once():
    today_str = datetime.datetime.now(chart_connector.IST).strftime("%Y-%m-%d")
    entries = campaign_connector.list_entries(active_only=True)
    pending = [
        e for e in entries
        if e.get("source") == "first_minute_movers"
        and (e.get("created_at") or "").startswith(today_str)
        and "entry_triggered" not in (e.get("milestones_notified") or [])
    ]
    if len(pending) < 2:
        return  # nothing to race against — a lone candidate just waits for the general bot

    # A tick can find more than one pending stock already past its entry
    # (prices move between 60s checks, and multiple can cross within the
    # same window) — collect every one that has crossed on this tick,
    # then pick the tightest stop-loss (lowest SL% = lowest risk) among
    # them as the single winner, rather than an arbitrary list-order
    # tiebreak. A stock that crossed on an earlier tick already won and
    # was removed from "pending" (entry_triggered set), so this only
    # ever compares stocks crossing for the first time on this same tick.
    crossed = []
    for entry in pending:
        entry_price = entry.get("entry_price")
        if entry_price is None:
            continue
        try:
            change = _symbol_change_pct(entry["symbol"])
        except Exception:
            change = None
        current_price = change["value"] if change else None
        if current_price is not None and current_price >= float(entry_price):
            sl_price_raw = entry.get("sl_price")
            sl_pct = None
            if sl_price_raw is not None and float(entry_price) > 0:
                sl_pct = (float(entry_price) - float(sl_price_raw)) / float(entry_price)
            crossed.append((entry, current_price, sl_pct))

    if not crossed:
        return

    crossed.sort(key=lambda c: c[2] if c[2] is not None else float("inf"))
    entry, current_price, _winner_sl_pct = crossed[0]
    entry_price = float(entry["entry_price"])
    sl_price = float(entry["sl_price"]) if entry.get("sl_price") is not None else None

    title, body = _milestone_message(entry["symbol"], "entry_triggered", entry_price, sl_price, current_price)
    try:
        _send_campaign_notification(
            title, body, ALERT_MONITOR_AUDIENCE, entry_symbols=[entry["symbol"]],
            channels=("in_app", "push") if fcm_connector.is_configured() else ("in_app",),
            sent_by="breakout-watch-bot",
        )
    except Exception as exc:
        print(f"[breakout-watch] notify failed for {entry['symbol']}: {exc}", file=sys.stderr)

    if AUTO_ORDER_ON_BREAKOUT_ENABLED:
        try:
            resolved, _unresolved = dhan_connector.resolve_security_ids([entry["symbol"]])
            security_id = resolved.get(entry["symbol"])
            if security_id is None:
                print(f"[breakout-watch] auto-order skipped for {entry['symbol']}: no security id", file=sys.stderr)
            else:
                intent = order_intent_connector.create_intent(
                    entry_id=entry["id"], symbol=entry["symbol"], security_id=security_id,
                    side="BUY", entry_price=entry_price, sl_price=sl_price,
                )
                if intent is not None:
                    order_intent_connector.trigger_order_executor()
                    print(f"[breakout-watch] order intent created + executor triggered for {entry['symbol']}", file=sys.stderr)
                # intent is None => an intent for this entry already exists (duplicate
                # _breakout_watch_once() run) — idempotency gate 1, silently a no-op.
        except Exception as exc:
            print(f"[breakout-watch] auto-order failed for {entry['symbol']}: {exc}", file=sys.stderr)

    already_notified = set(entry.get("milestones_notified") or [])
    try:
        campaign_connector.update_entry(entry["id"], milestones_notified=list(already_notified | {"entry_triggered"}))
    except Exception as exc:
        print(f"[breakout-watch] couldn't persist milestone for {entry['symbol']}: {exc}", file=sys.stderr)

    losers = [e for e in pending if e["id"] != entry["id"]]
    for loser in losers:
        try:
            campaign_connector.update_entry(
                loser["id"], active=False,
                note=(loser.get("note") or "") + f" [cancelled - {entry['symbol']} won (lowest SL%, entry triggered at {current_price:.2f})]",
            )
        except Exception as exc:
            print(f"[breakout-watch] couldn't deactivate {loser['symbol']}: {exc}", file=sys.stderr)

    # A winner for the day means "only take the first stock that breaks
    # out" is now decided — also stop the separate qualification process
    # (_auto_create_breakout_alerts) so a stock still waiting on 2nd-
    # candle data at this exact moment can't qualify a minute later and
    # become a brand-new solo watch with nothing left to race against
    # (it would otherwise go on to trigger its own independent entry,
    # defeating the whole point of the race). Safe across a day boundary:
    # _auto_create_breakout_alerts() resets this state itself the moment
    # it sees a new date.
    if _auto_breakout_state["date"] == today_str:
        _auto_breakout_state["done"] = True
        _save_auto_breakout_state()

    print(f"[breakout-watch] {today_str}: {entry['symbol']} won (lowest SL%, entry triggered at {current_price:.2f}) among {len(crossed)} crossed this tick - cancelled {[l['symbol'] for l in losers]}, qualification stopped for today", file=sys.stderr)


def _breakout_watch_loop():
    while True:
        try:
            if _market_status().startswith("Markets open"):
                # Qualify (does today's frozen top-4 pick's 2nd candle turn
                # out red?) and watch (has a qualified stock's price
                # crossed its entry?) now share one fast, 1-minute cadence
                # — a stock that only just qualified gets its first
                # breakout check on this very same tick, not up to
                # ALERT_MONITOR_INTERVAL_SECONDS (5 min) later.
                _auto_create_breakout_alerts()
                _breakout_watch_once()
        except Exception as exc:
            print(f"[breakout-watch] check cycle failed: {exc}", file=sys.stderr)
        time.sleep(BREAKOUT_WATCH_INTERVAL_SECONDS)


def _start_breakout_watch():
    threading.Thread(target=_breakout_watch_loop, daemon=True, name="breakout-watch").start()


@app.get("/api/admin/campaign/tracker")
@role_required("admin")
def api_admin_campaign_tracker():
    entries = campaign_connector.list_entries(active_only=True)
    with ThreadPoolExecutor(max_workers=min(20, max(1, len(entries)))) as pool:
        states = list(pool.map(_entry_tracker_state, entries))
    return jsonify({"entries": states})


@app.post("/api/admin/campaign-notifications/<notification_id>/delete")
@role_required("admin")
def api_admin_delete_notification(notification_id):
    # quantile-notifications doubles as every subscriber's in-app feed
    # (GET /api/notifications/recent) — deleting here pulls it out of their
    # inbox too, not just the admin's own send history.
    campaign_connector.delete_notification(notification_id)
    return jsonify({"ok": True})


@app.post("/api/admin/campaign-notifications/delete-batch")
@role_required("admin")
def api_admin_delete_notifications_batch():
    data = request.get_json(silent=True) or {}
    ids = [i for i in (data.get("ids") or []) if i]
    if not ids:
        return jsonify({"error": "No campaigns selected."}), 400
    campaign_connector.delete_notifications(ids)
    return jsonify({"ok": True, "deleted": len(ids)})


@app.get("/api/notifications/recent")
@login_required
def api_notifications_recent():
    user = _current_user()
    plan = subscription_connector.get_subscription(user["email"])["plan"]
    # Fetch more than the 10 we'll show, then filter by the viewer's own
    # plan and re-truncate — filtering AFTER a plain limit=10 fetch could
    # leave a Free viewer with fewer than 10 even when 10+ apply to them,
    # if some of the most recent ones were Pro/Premium-only. Missing
    # "audience" (rows from before this field existed) means "everyone".
    items = campaign_connector.list_recent_notifications(limit=30)
    items = [n for n in items if plan in (n.get("audience") or ["free", "pro", "premium"])]
    return jsonify(items[:10])


@app.post("/api/push/register-token")
@login_required
def api_push_register_token():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    if not token:
        return jsonify({"error": "Missing token."}), 400
    campaign_connector.register_push_token(token, user["email"])
    return jsonify({"ok": True})


@app.post("/api/push/unregister-token")
@login_required
def api_push_unregister_token():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    if token:
        campaign_connector.remove_push_token(token)
    return jsonify({"ok": True})


@app.get("/api/push/config")
def api_push_config():
    """Public — firebaseConfig and the VAPID key are meant to ship in
    browser JS (they identify the Firebase project, they don't grant any
    access by themselves); the actual secret (service-account key) never
    leaves connectors/fcm_connector.py's server-side calls."""
    if not fcm_connector.is_configured():
        return jsonify({"configured": False})
    return jsonify({
        "configured": True,
        "firebaseConfig": json.loads(secrets.get_parameter("/chartink-momentum-ai/fcm/web_config_json")),
        "vapidKey": secrets.get_parameter("/chartink-momentum-ai/fcm/vapid_public_key"),
    })


@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    # Served at the origin root (not /static/js/...) so the service
    # worker's default scope covers the whole site — Firebase's own web-push
    # setup expects it at exactly this path.
    #
    # The config is baked into the script HERE (server-rendered), not
    # fetched at runtime by the worker itself. A service worker is
    # terminated between events to save resources; when a push wakes a cold
    # worker, the browser dispatches that `push` event as soon as the
    # script starts evaluating. onBackgroundMessage() is what actually
    # attaches the real `push` listener under the hood — if that call sits
    # behind an async fetch().then(), the wake-up push can arrive before
    # the listener exists yet and gets silently dropped: no error, no
    # Action Center entry, nothing shows up anywhere. Doing it synchronously
    # in the worker's first script pass guarantees the listener is attached
    # before any push event this SW is woken by can be missed.
    if not fcm_connector.is_configured():
        return Response("// Push notifications are not configured.", mimetype="application/javascript")

    firebase_config = json.loads(secrets.get_parameter("/chartink-momentum-ai/fcm/web_config_json"))
    js = (
        'importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");\n'
        'importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");\n\n'
        'self.addEventListener("install", () => self.skipWaiting());\n'
        'self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));\n\n'
        f'firebase.initializeApp({json.dumps(firebase_config)});\n'
        'const messaging = firebase.messaging();\n'
        'messaging.onBackgroundMessage((payload) => {\n'
        '  const title = (payload.notification && payload.notification.title) || "Quantile";\n'
        '  const body = (payload.notification && payload.notification.body) || "";\n'
        # The click-target URL travels in the invisible `data` field (set
        # server-side from the campaign's "View Chart" CTA, see app.py's
        # _split_cta_for_push) rather than appearing as text in `body` —
        # that is what lets the visible notification show a clean label
        # instead of a raw link. A body-text URL match is kept only as a
        # fallback for anything that did not go through that path.
        '  const dataUrl = payload.data && payload.data.url;\n'
        '  const ctaLabel = payload.data && payload.data.cta_label;\n'
        '  const urlMatch = body.match(/https?:\\/\\/\\S+/);\n'
        '  const url = dataUrl || (urlMatch ? urlMatch[0] : self.location.origin);\n'
        # Android Chrome can render a background-push notification as
        # blank/near-invisible (or suppress it in some notification-shade
        # layouts) when showNotification() gets no icon - desktop Chrome
        # falls back to a default icon fine, Android does not. Absolute
        # path so it resolves the same regardless of where the SW itself
        # is served from.
        '  const options = { body: body, icon: "/favicon.svg", badge: "/favicon.svg", data: { url: url } };\n'
        # `actions` is ONLY honored on a service-worker-shown notification
        # (never on the foreground `new Notification()` path in
        # push-notifications.js — the spec doesn't support actions there
        # at all), and only when there is an actual CTA to act on —
        # otherwise a plain announcement would get a stray empty button.
        '  if (dataUrl && ctaLabel) {\n'
        '    options.actions = [{ action: "view_chart", title: ctaLabel }];\n'
        '  }\n'
        '  self.registration.showNotification(title, options);\n'
        '});\n\n'
        # Fires for BOTH the action button and a tap on the notification
        # body itself — event.action is "view_chart" for the button, ""
        # for a plain body tap, and either way the destination is the
        # same single URL, so no need to branch on event.action here.
        # (A notification with no click handler at all is a dead end —
        # tapping it did nothing before this fix.)
        'self.addEventListener("notificationclick", (event) => {\n'
        '  event.notification.close();\n'
        '  const url = (event.notification.data && event.notification.data.url) || self.location.origin;\n'
        '  event.waitUntil(\n'
        '    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {\n'
        '      for (const client of clientList) {\n'
        '        if (client.url === url && "focus" in client) return client.focus();\n'
        '      }\n'
        '      return self.clients.openWindow(url);\n'
        '    })\n'
        '  );\n'
        '});\n'
    )
    return Response(js, mimetype="application/javascript")


# ============================================================
# API
# ============================================================

@app.get("/api/scanners")
@subscription_required
def api_scanners():

    return jsonify([
        {"id": sid, "name": s["name"], "description": s["description"]}
        for sid, s in SCANNERS.items()
    ])


def _scanner_cache_key(scanner_id):
    return f"scanner_{scanner_id}"


@app.get("/api/scanners/<scanner_id>/cached")
@subscription_required
def api_cached_scanner(scanner_id):
    """Last cached result for a scanner, if any — never triggers a live
    run, so selecting a scanner can show its last-known result instantly
    without that counting as "running" it."""
    scanner = SCANNERS.get(scanner_id)

    if scanner is None:
        abort(404, description=f"Unknown scanner: {scanner_id}")

    entry = cache.peek(_scanner_cache_key(scanner_id))
    if entry is None:
        return jsonify({"cached": False})

    result = dict(entry["data"])
    result["scanner_id"] = scanner_id
    result["scanner_name"] = scanner["name"]
    result["generated_at"] = datetime.datetime.fromtimestamp(entry["cached_at"], tz=chart_connector.IST).strftime("%d %b, %I:%M %p")
    result["error"] = None
    result["cached"] = True
    return jsonify(result)


@app.get("/api/scanners/<scanner_id>/run")
@subscription_required
def api_run_scanner(scanner_id):

    scanner = SCANNERS.get(scanner_id)

    if scanner is None:
        abort(404, description=f"Unknown scanner: {scanner_id}")

    cache_key = _scanner_cache_key(scanner_id)

    try:
        # force=True: this is the explicit "Run scanner" action, not the
        # passive /cached view — a click here should always do real work,
        # not silently hand back a same-looking result from up to
        # SCAN_CACHE_TTL_SECONDS ago with no indication nothing actually
        # ran. Still writes through to the same cache /cached reads from.
        result = cache.get_or_fetch(cache_key, SCAN_CACHE_TTL_SECONDS, scanner["run"], force=True)
    except Exception as exc:
        return jsonify({
            "scanner_id": scanner_id,
            "scanner_name": scanner["name"],
            "generated_at": datetime.datetime.now(chart_connector.IST).strftime("%d %b, %I:%M %p"),
            "error": str(exc),
        }), 502

    entry = cache.peek(cache_key)
    generated_at = (
        datetime.datetime.fromtimestamp(entry["cached_at"], tz=chart_connector.IST).strftime("%d %b, %I:%M %p")
        if entry else datetime.datetime.now(chart_connector.IST).strftime("%d %b, %I:%M %p")
    )

    result = dict(result)
    result["scanner_id"] = scanner_id
    result["scanner_name"] = scanner["name"]
    result["generated_at"] = generated_at
    result["error"] = None

    return jsonify(result)


if __name__ == "__main__":
    # The alert-tracking bot runs on its own daemon thread for the life of
    # this process — started here (not at module import time) so it
    # doesn't also spin up under a WSGI import or a test-client import of
    # this module. use_reloader=False below means this module only ever
    # executes __main__ once per real process, so there's no risk of
    # starting a second monitor thread on a reloader respawn either.
    _start_alert_monitor()
    _start_breakout_watch()

    # threaded=True lets the dev server actually parallelize the concurrent
    # per-symbol fetches the Chart Wall's EMA cross filter issues (356
    # stocks, 8 at a time) instead of serializing every request.
    # use_reloader=False: the reloader spawns a child process on Windows
    # rather than exec-replacing itself, so killing the tracked PID leaves
    # an orphaned server still bound to the port — these accumulate across
    # restarts during dev. Restart manually (kill + rerun) after edits.
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)
