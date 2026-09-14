"""Razorpay integration — real recurring billing for paid plans.

Uses plain `requests` with HTTP Basic Auth (Key ID as username, Key Secret
as password) rather than the `razorpay` PyPI SDK: Razorpay's REST API is
simple enough that a dedicated SDK isn't worth another dependency (this
project has already hit real pip-install friction from Windows MAX_PATH —
see connectors/secrets.py's neighbors), and every other external API this
project talks to (Dhan's public CSVs, screener.in, marketsmithindia.com)
already goes through plain `requests`.

Credentials come from SSM (connectors/secrets.py), same pattern as every
other credential here:
  /chartink-momentum-ai/razorpay/key_id
  /chartink-momentum-ai/razorpay/key_secret
  /chartink-momentum-ai/razorpay/webhook_secret
  /chartink-momentum-ai/razorpay/plan_pro_id       (from setup_razorpay.py)
  /chartink-momentum-ai/razorpay/plan_premium_id   (from setup_razorpay.py)

None of these exist until a real Razorpay account provides test-mode keys —
until then, is_configured() is False and callers fall back to the voucher
path (subscription_connector.redeem_voucher), which needs no gateway at
all. This module is unexercised against a live Razorpay account as of
writing; the request shapes follow Razorpay's documented Subscriptions API
(stable, well-established), but treat the first live call as the real test.
"""

import hashlib
import hmac

import boto3
import requests

from connectors import secrets

API_BASE = "https://api.razorpay.com/v1"
AWS_REGION = "ap-south-1"
_configured = None
_creds = None


class RazorpayError(Exception):
    pass


def is_configured():
    global _configured
    if _configured is None:
        try:
            secrets.get_parameter("/chartink-momentum-ai/razorpay/key_id")
            _configured = True
        except Exception:
            _configured = False
    return _configured


def _get_creds():
    global _creds
    if _creds is None:
        _creds = (
            secrets.get_parameter("/chartink-momentum-ai/razorpay/key_id"),
            secrets.get_parameter("/chartink-momentum-ai/razorpay/key_secret"),
        )
    return _creds


def _request(method, path, **kwargs):
    response = requests.request(method, f"{API_BASE}{path}", auth=_get_creds(), timeout=20, **kwargs)
    if not response.ok:
        detail = response.json().get("error", {}).get("description", response.text) if response.content else response.text
        raise RazorpayError(f"Razorpay {method} {path} failed: {detail}")
    return response.json()


def get_plan_id(internal_plan_id):
    """Maps our own "pro"/"premium" plan ids to Razorpay's plan_XXXXX ids,
    created once by setup_razorpay.py and stored in SSM — Razorpay Plans
    are immutable (price changes need a new Plan), so there's no reason to
    create one per checkout."""
    param = {
        "pro": "/chartink-momentum-ai/razorpay/plan_pro_id",
        "premium": "/chartink-momentum-ai/razorpay/plan_premium_id",
    }.get(internal_plan_id)
    if param is None:
        raise RazorpayError(f"No Razorpay plan configured for {internal_plan_id!r}")
    try:
        return secrets.get_parameter(param)
    except Exception as exc:
        raise RazorpayError(f"Razorpay plan for {internal_plan_id!r} isn't set up yet — run setup_razorpay.py") from exc


def create_plan(name, amount_paise, internal_plan_id):
    """One-time plan creation — see setup_razorpay.py. Razorpay Plans are
    immutable, so this should only ever run once per internal_plan_id; a
    price change means creating a new plan, not editing this one."""
    return _request("POST", "/plans", json={
        "period": "monthly",
        "interval": 1,
        "item": {"name": name, "amount": amount_paise, "currency": "INR"},
        "notes": {"internal_plan_id": internal_plan_id},
    })


def _put_ssm_param(name, value):
    boto3.client("ssm", region_name=AWS_REGION).put_parameter(Name=name, Value=value, Type="String", Overwrite=True)


def get_or_create_discounted_plan(internal_plan_id, percent_off, base_price_paise, plan_display_name):
    """A <100%-off voucher campaign (connectors/subscription_connector.py's
    admin-managed campaigns) needs an actual reduced-price charge —
    Razorpay Plans are immutable/fixed-price, so there's no "apply a
    coupon" parameter on subscription creation; the discount has to be its
    own Plan. Created lazily on first use per (plan, percent) pair and
    cached in SSM, so redeeming the same campaign repeatedly reuses one
    Plan instead of creating a new one every checkout. Note this discounts
    every billing cycle for the life of the subscription, not just the
    first one — there's no per-cycle coupon concept here, only per-plan
    pricing."""
    discounted_amount = round(base_price_paise * (100 - percent_off) / 100)
    param = f"/chartink-momentum-ai/razorpay/plan_{internal_plan_id}_off{percent_off}_id"
    try:
        return secrets.get_parameter(param)
    except Exception:
        pass
    response = create_plan(f"{plan_display_name} ({percent_off}% off)", discounted_amount, f"{internal_plan_id}_off{percent_off}")
    _put_ssm_param(param, response["id"])
    return response["id"]


def create_subscription(internal_plan_id, email, name, discount=None):
    """Starts a real subscription in "created" state — the customer still
    has to authorize it via Razorpay Checkout.js on the frontend (using the
    returned id) before it becomes "active". total_count=120 means up to
    120 monthly charges (10 years); Razorpay requires a finite count, there
    is no literal "forever" option.

    `discount`, if given, is {"percent_off", "base_price_paise", "plan_name",
    "voucher_code"} — routes the subscription to a discounted Plan instead
    of the standard one via get_or_create_discounted_plan()."""
    if discount:
        plan_id = get_or_create_discounted_plan(
            internal_plan_id, discount["percent_off"], discount["base_price_paise"], discount["plan_name"],
        )
    else:
        plan_id = get_plan_id(internal_plan_id)

    notes = {"email": email, "name": name, "internal_plan_id": internal_plan_id}
    if discount:
        notes["voucher_code"] = discount["voucher_code"]

    return _request("POST", "/subscriptions", json={
        "plan_id": plan_id,
        "customer_notify": 1,
        "total_count": 120,
        "notes": notes,
    })


def fetch_subscription(razorpay_subscription_id):
    return _request("GET", f"/subscriptions/{razorpay_subscription_id}")


def cancel_subscription(razorpay_subscription_id):
    """cancel_at_cycle_end=1 matches this app's own cancellation semantics
    (access continues until the current paid period ends)."""
    return _request("POST", f"/subscriptions/{razorpay_subscription_id}/cancel", json={"cancel_at_cycle_end": 1})


def verify_payment_signature(razorpay_subscription_id, razorpay_payment_id, razorpay_signature):
    """Per Razorpay's docs: HMAC-SHA256 of "payment_id|subscription_id",
    keyed with the Key Secret — called right after Checkout.js's success
    callback hands back these three values, before trusting the payment."""
    _, key_secret = _get_creds()
    message = f"{razorpay_payment_id}|{razorpay_subscription_id}".encode("utf-8")
    expected = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


def verify_webhook_signature(raw_body, signature_header):
    webhook_secret = secrets.get_parameter("/chartink-momentum-ai/razorpay/webhook_secret")
    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")
