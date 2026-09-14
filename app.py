import csv
import datetime
import decimal
import functools
import io
import json
import os
import random
import re
import string
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for

import chartink_stoch_backtest as stoch_mod
import dhan_ema_breakout as dhan_ema_mod
import mock_data
from connectors import ai_verdict, auth_verify, cache, campaign_ai, campaign_connector, chart_connector, cognito_connector, fcm_connector, fundamentals_connector, ipo_connector, marketsmith_connector, news_connector, razorpay_connector, secrets, stock_screener_ai, subscription_connector

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
    # a redirect to the HTML /login page is a page-navigation concept that
    # doesn't mean anything to a fetch() caller.
    return request.path.startswith("/api/")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if _current_user() is None:
            if _is_api_request():
                return jsonify({"error": "Not authenticated."}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Like login_required, but also requires the signed-in user's role to
    be one of `roles` — a wrong-role (but signed-in) user gets a 403 page
    (or 403 JSON for an API call) rather than being bounced back to the
    login form they already passed."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user is None:
                if _is_api_request():
                    return jsonify({"error": "Not authenticated."}), 401
                return redirect(url_for("login", next=request.path))
            if user["role"] not in roles:
                if _is_api_request():
                    return jsonify({"error": "Forbidden."}), 403
                return render_template("access_denied.html"), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_current_user():
    return {"current_user": _current_user()}


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


@app.post("/api/auth/signup")
def api_auth_signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    if not email or not password or not name:
        return jsonify({"error": "Name, email and password are required."}), 400
    try:
        cognito_connector.sign_up(email, password, name)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/auth/confirm")
def api_auth_confirm():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not email or not code:
        return jsonify({"error": "Enter the verification code."}), 400
    try:
        cognito_connector.confirm_sign_up(email, code)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/auth/resend-code")
def api_auth_resend_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400
    try:
        cognito_connector.resend_confirmation_code(email)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/auth/login")
def api_auth_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    try:
        tokens = cognito_connector.sign_in(email, password)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 401
    _store_tokens(email, tokens)
    next_path = data.get("next") or url_for("subscriber_dashboard")
    return jsonify({"ok": True, "redirect": next_path})


@app.post("/api/auth/logout")
def api_auth_logout():
    access_token = session.get("access_token")
    if access_token:
        cognito_connector.global_sign_out(access_token)
    session.clear()
    return jsonify({"ok": True, "redirect": url_for("login")})


@app.post("/api/auth/forgot-password")
def api_auth_forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400
    try:
        cognito_connector.forgot_password(email)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/auth/reset-password")
def api_auth_reset_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_password = data.get("password") or ""
    if not email or not code or not new_password:
        return jsonify({"error": "All fields are required."}), 400
    try:
        cognito_connector.confirm_forgot_password(email, code, new_password)
    except cognito_connector.AuthError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


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


SCANNERS = {
    "stoch": {
        "name": "Stochastic Crossover",
        "description": (
            "%K/%D(4,3) cross above 20, RSI(14) below 50, close below "
            "EMA(50) — live scan combined with the last 10 backtest days"
        ),
        "run": run_stoch,
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
}

# Scan results are cached rather than re-run on every request — running a
# scanner re-hits the live upstream source (Chartink or the S3 EOD dump),
# which is slow and doesn't change meaningfully within a few minutes.
SCAN_CACHE_TTL_SECONDS = 5 * 60


# ============================================================
# PAGES
# ============================================================

@app.route("/")
def home():
    return render_template("home.html", **mock_data.home_data())


@app.route("/scanner")
def scanner_page():

    selected_id = request.args.get("id", "")

    if selected_id not in SCANNERS:
        selected_id = ""

    return render_template(
        "scanner.html",
        scanners=SCANNERS,
        selected_id=selected_id,
    )


@app.route("/news")
def news():
    try:
        data = news_connector.get_news_data()
        # gainers/losers need a live quotes feed, not a news connector concern
        data["gainers"] = mock_data.news_data()["gainers"]
        data["losers"] = mock_data.news_data()["losers"]
    except Exception:
        app.logger.exception("news connector failed")
        data = {"stories": [], "trending": [], "gainers": [], "losers": [], "unavailable": True}
    return render_template("news.html", **data)


@app.route("/capabilities")
def capabilities():
    return render_template("capabilities.html", **mock_data.capabilities_data())


@app.route("/education")
def education():
    return render_template("education.html", **mock_data.education_data())


@app.route("/pricing")
def pricing():
    return render_template("pricing.html", **mock_data.pricing_data())


@app.route("/vision")
def vision():
    return render_template("vision.html", **mock_data.vision_data())


@app.route("/markets/ipo-hub")
def ipo_hub():
    try:
        data = ipo_connector.get_ipo_hub_data()
    except Exception:
        app.logger.exception("IPO connector failed")
        data = {"ipos": [], "subCategories": [], "unavailable": True}
    return render_template("ipo_hub.html", **data)


def _normalize_symbol(raw):
    # NSE/BSE tickers never contain spaces, so "HDFC Bank" -> "HDFCBANK"
    # and "TATA STEEL" -> "TATASTEEL" resolve correctly on screener.in
    # even though users naturally type the company name with spaces.
    return (raw or "HDFCBANK").strip().upper().replace(" ", "")


@app.route("/markets/research")
def research():
    symbol = _normalize_symbol(request.args.get("symbol"))
    try:
        data = fundamentals_connector.get_research_data(symbol)
        # same screener.in page backs both, so this reads from cache rather
        # than triggering a second fetch (see fundamentals_connector._get_raw)
        data.update(fundamentals_connector.get_fundamentals_data(symbol))
    except RuntimeError:
        return render_template("research.html", symbol=symbol, not_found=True)
    except Exception:
        app.logger.exception("fundamentals connector failed for %s", symbol)
        return render_template("research.html", symbol=symbol, unavailable=True)

    try:
        data.update(marketsmith_connector.get_strength_ratings(symbol))
    except Exception:
        # best-effort supplementary rating, not core to the page
        app.logger.exception("marketsmith connector failed for %s", symbol)

    try:
        data["priceHistory"] = fundamentals_connector.get_price_history(symbol)
    except Exception:
        # best-effort — page works fine without the chart
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
        # best-effort — page works fine without the AI summary
        app.logger.exception("AI verdict generation failed for %s", symbol)

    return render_template("research.html", **data)


POPULAR_INDICES = ["NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA"]


@app.route("/markets/chart")
def chart_page():
    try:
        symbols = chart_connector.get_top_symbols_cached(limit=200)
    except Exception:
        app.logger.exception("chart symbol list fetch failed")
        symbols = []

    requested = _normalize_symbol(request.args.get("symbol")) if request.args.get("symbol") else None
    symbol = requested or (symbols[0]["symbol"] if symbols else None)

    if symbol is None:
        return render_template("chart.html", symbols=[], indices=POPULAR_INDICES, unavailable=True)

    try:
        bars = chart_connector.get_ohlcv(symbol)
    except LookupError:
        return render_template("chart.html", symbols=symbols, indices=POPULAR_INDICES, symbol=symbol, not_found=True, unavailable=False)
    except Exception:
        app.logger.exception("chart data fetch failed for %s", symbol)
        return render_template("chart.html", symbols=symbols, indices=POPULAR_INDICES, symbol=symbol, unavailable=True)

    return render_template("chart.html", symbols=symbols, indices=POPULAR_INDICES, symbol=symbol, bars=bars, unavailable=False)


@app.get("/api/chart/data")
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


@app.route("/markets/chart-wall")
def chart_wall_page():
    try:
        stocks = chart_connector.get_watchlist_stocks_cached()
    except Exception:
        app.logger.exception("chart wall stock list fetch failed")
        stocks = []
        unavailable = True
    else:
        unavailable = False

    return render_template("chart_wall.html", stocks=stocks, unavailable=unavailable)


@app.route("/login")
def login():
    if _current_user():
        return redirect(url_for("subscriber_dashboard"))
    return render_template("login.html", next_path=request.args.get("next") or "")


@app.route("/payment")
def payment():
    # The old static fake-checkout page — real checkout now lives on
    # /subscription (Razorpay Checkout.js opens as an overlay there, it
    # isn't a separate page), so this just forwards old links/bookmarks.
    return redirect(url_for("subscription_page"))


@app.route("/subscription")
@login_required
def subscription_page():
    user = _current_user()
    sub = subscription_connector.get_subscription(user["email"])
    return render_template(
        "subscription.html",
        subscription=sub,
        plans=subscription_connector.PLANS,
        visible_campaigns=subscription_connector.list_visible_campaigns(),
        razorpay_configured=razorpay_connector.is_configured(),
        razorpay_key_id=(secrets.get_parameter("/chartink-momentum-ai/razorpay/key_id") if razorpay_connector.is_configured() else None),
    )


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


def _dashboard_watchlist(limit=10):
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


def _dashboard_scan_results(limit=4):
    """Last cached EMA 10/20 Breakout result, if the scanner has been run
    at least once — read-only (cache.peek), same as the scanner page's own
    "show cached, don't auto-run" behavior. None if it's never been run."""
    entry = cache.peek(_scanner_cache_key("dhan_ema_breakout"))
    if not entry:
        return None
    return {
        "rows": entry["data"].get("rows", [])[:limit],
        "generated_at": datetime.datetime.fromtimestamp(entry["cached_at"]).strftime("%d %b, %I:%M %p"),
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


@app.route("/dashboard")
@login_required
def subscriber_dashboard():
    user = _current_user()
    data = mock_data.subscriber_dashboard_data()
    data["today"] = datetime.datetime.now(chart_connector.IST).strftime("%A, %d %b %Y")
    data["marketStatus"] = _market_status()
    data["watchlist"] = _dashboard_watchlist()
    data["scanResults"] = _dashboard_scan_results()
    data["educationCourses"] = [
        c for c in mock_data.education_data()["courses"]
        if c["title"] in ("Technical Analysis Foundations", "IPO Investing Playbook")
    ]
    try:
        data["memberSince"] = _cached_member_since(user["email"])
    except Exception:
        data["memberSince"] = None
    data["subscription"] = subscription_connector.get_subscription(user["email"])
    data["recentAlerts"] = _dashboard_recent_alerts(data["subscription"]["plan"])
    # Market indices/sector-momentum/breadth are NOT fetched here. Each
    # one individually calls out to S3/Dhan per symbol (indices: 3 calls,
    # sectors: 5, breadth: 30) — on a cold cache that's measured at
    # several seconds up to ~75s for breadth alone, none of which should
    # ever block the page load. They're loaded together, in parallel, from
    # /api/dashboard/market-snapshot after the page renders instead (see
    # the dashboard's own script) — same "render first, fill in the slow
    # part after" pattern as the scanner pages' cached-vs-run split.
    return render_template("subscriber_dashboard.html", **data)


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


ADMIN_NAV_ITEMS = [
    {"label": "Overview", "endpoint": "admin_dashboard"},
    {"label": "Users", "endpoint": "admin_users_page"},
    {"label": "Subscriptions", "endpoint": "admin_subscriptions_page"},
    {"label": "Voucher Campaigns", "endpoint": "admin_campaigns_page"},
    {"label": "Scanner Campaign", "endpoint": "admin_scanner_campaign_page"},
    {"label": "IPO Data", "endpoint": "ipo_hub"},
    {"label": "Courses", "endpoint": "education"},
]


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


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    users = cognito_connector.list_all_users()
    stats = subscription_connector.compute_revenue_stats(len(users))
    recent_users = [_user_with_subscription(dict(u)) for u in users[:6]]
    admin_count = sum(1 for u in users if u["role"] == "admin")

    return render_template(
        "admin_dashboard.html",
        nav_items=ADMIN_NAV_ITEMS,
        active_admin_tab="Overview",
        stats=stats,
        recent_users=recent_users,
        total_user_count=len(users),
        admin_count=admin_count,
    )


@app.route("/admin/users")
@role_required("admin")
def admin_users_page():
    users = [_user_with_subscription(dict(u)) for u in cognito_connector.list_all_users()]
    return render_template(
        "admin_users.html",
        nav_items=ADMIN_NAV_ITEMS,
        active_admin_tab="Users",
        users=users,
    )


@app.post("/api/admin/users/<email>/role")
@role_required("admin")
def api_admin_set_user_role(email):
    data = request.get_json(silent=True) or {}
    if email == _current_user()["email"] and not data.get("admin", True):
        return jsonify({"error": "You can't remove your own admin access."}), 400
    cognito_connector.set_admin(email, bool(data.get("admin")))
    return jsonify({"ok": True})


@app.post("/api/admin/users/<email>/enabled")
@role_required("admin")
def api_admin_set_user_enabled(email):
    data = request.get_json(silent=True) or {}
    if email == _current_user()["email"] and not data.get("enabled", True):
        return jsonify({"error": "You can't disable your own account."}), 400
    cognito_connector.set_enabled(email, bool(data.get("enabled")))
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
    return jsonify({"ok": True, "email": email, "password": password})


@app.get("/admin/users/export.csv")
@role_required("admin")
def admin_users_export_csv():
    users = [_user_with_subscription(dict(u)) for u in cognito_connector.list_all_users()]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Email", "Name", "Role", "Confirmed", "Plan", "Subscription Status", "Joined"])
    for u in users:
        writer.writerow([
            u["email"], u["name"], u["role"], u["confirmed"], u["plan"], u["sub_status"],
            u["created_at"].strftime("%Y-%m-%d"),
        ])
    response = app.response_class(buf.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=quantile-users.csv"
    return response


@app.route("/admin/subscriptions")
@role_required("admin")
def admin_subscriptions_page():
    return render_template(
        "admin_subscriptions.html",
        nav_items=ADMIN_NAV_ITEMS,
        active_admin_tab="Subscriptions",
        subscriptions=subscription_connector.list_all_subscriptions(),
    )


@app.route("/admin/campaigns")
@role_required("admin")
def admin_campaigns_page():
    return render_template(
        "admin_campaigns.html",
        nav_items=ADMIN_NAV_ITEMS,
        active_admin_tab="Voucher Campaigns",
        campaigns=subscription_connector.list_campaigns(),
        plans=subscription_connector.PLANS,
    )


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


@app.route("/admin/scanner-campaign")
@role_required("admin")
def admin_scanner_campaign_page():
    scanner_results = {}
    for scanner_id, scanner in SCANNERS.items():
        entry = cache.peek(_scanner_cache_key(scanner_id))
        scanner_results[scanner_id] = {
            "name": scanner["name"],
            "columns": entry["data"].get("columns", []) if entry else None,
            "rows": entry["data"].get("rows", []) if entry else None,
            "generated_at": (
                datetime.datetime.fromtimestamp(entry["cached_at"]).strftime("%d %b, %I:%M %p") if entry else None
            ),
        }

    templates = campaign_connector.list_templates()
    if not templates:
        # First-ever visit to this page (or every saved template has since
        # been deleted) — seed a "Default" template from the values that
        # used to just be hardcoded into the form, so there's always at
        # least one real, loadable/deletable template instead of a blank
        # dropdown, and the admin's existing message isn't lost by moving
        # to a template system.
        campaign_connector.create_template(
            name="Default",
            title="",
            header="",
            entry_line_template="{{symbol}} — Entry {{entry}}, SL {{sl}}, Target {{target}}",
            footer="⚠️ This is for educational purposes only. Not a buy/sell recommendation. Trade at your own risk.",
            created_by="system",
        )
        templates = campaign_connector.list_templates()

    return render_template(
        "admin_scanner_campaign.html",
        nav_items=ADMIN_NAV_ITEMS,
        active_admin_tab="Scanner Campaign",
        scanners=SCANNERS,
        scanner_results=scanner_results,
        entries=campaign_connector.list_entries(),
        notifications=campaign_connector.list_recent_notifications(),
        templates=templates,
        push_configured=fcm_connector.is_configured(),
        push_token_count=len(campaign_connector.list_all_push_tokens()),
    )


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


def _milestones_reached(entry_price, sl_price, current_price):
    """Every milestone `current_price` currently qualifies for — not just
    the newest one, since a single check can jump straight past several
    at once (e.g. a gap-up open past both the entry and 1:1 levels)."""
    reached = set()
    if entry_price is None or entry_price <= 0:
        return reached

    if current_price >= entry_price:
        reached.add("entry_triggered")

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


def _milestone_message(symbol, milestone, entry_price, sl_price, current_price):
    if milestone == "entry_triggered":
        return (
            f"🔔 Entry triggered — {symbol}",
            f"{symbol} has crossed your entry price of ₹{entry_price:.2f} (now ₹{current_price:.2f}).",
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

    reached = _milestones_reached(entry_price, sl_price, current_price) if (entry_price and current_price) else set()
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
        reached = _milestones_reached(entry_price, sl_price, current_price)
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
        '  const options = { body: body, data: { url: url } };\n'
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
def api_scanners():

    return jsonify([
        {"id": sid, "name": s["name"], "description": s["description"]}
        for sid, s in SCANNERS.items()
    ])


def _scanner_cache_key(scanner_id):
    return f"scanner_{scanner_id}"


@app.get("/api/scanners/<scanner_id>/cached")
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
    result["generated_at"] = datetime.datetime.fromtimestamp(entry["cached_at"]).isoformat(timespec="seconds")
    result["error"] = None
    result["cached"] = True
    return jsonify(result)


@app.get("/api/scanners/<scanner_id>/run")
def api_run_scanner(scanner_id):

    scanner = SCANNERS.get(scanner_id)

    if scanner is None:
        abort(404, description=f"Unknown scanner: {scanner_id}")

    cache_key = _scanner_cache_key(scanner_id)

    try:
        result = cache.get_or_fetch(cache_key, SCAN_CACHE_TTL_SECONDS, scanner["run"])
    except Exception as exc:
        return jsonify({
            "scanner_id": scanner_id,
            "scanner_name": scanner["name"],
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "error": str(exc),
        }), 502

    entry = cache.peek(cache_key)
    generated_at = (
        datetime.datetime.fromtimestamp(entry["cached_at"]).isoformat(timespec="seconds")
        if entry else datetime.datetime.now().isoformat(timespec="seconds")
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

    # threaded=True lets the dev server actually parallelize the concurrent
    # per-symbol fetches the Chart Wall's EMA cross filter issues (356
    # stocks, 8 at a time) instead of serializing every request.
    # use_reloader=False: the reloader spawns a child process on Windows
    # rather than exec-replacing itself, so killing the tracked PID leaves
    # an orphaned server still bound to the port — these accumulate across
    # restarts during dev. Restart manually (kill + rerun) after edits.
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)
