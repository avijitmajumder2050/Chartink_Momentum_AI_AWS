"""Real subscription records — plan, status, Razorpay linkage — stored in
DynamoDB (table "quantile-subscriptions", partition key "email"). Cognito
tracks identity/role; this tracks billing state, which is a different
shape of data (mutable, event-driven, needs a history trail) that doesn't
fit Cognito's user-attribute model well.

Every user who's never subscribed effectively has a "free" record even
though nothing is written to the table for them yet (get_subscription()
synthesizes one) — a row only gets created the first time someone redeems
a voucher or completes real checkout.

Cancellation is "at period end", matching the pricing page's own FAQ
("you keep access until the end of the billing period"): cancel_subscription
sets status to "canceled" but leaves `plan` alone; get_subscription() lazily
flips a canceled, expired record back to the free plan on read rather than
needing a cron job to do it.
"""

import datetime

import boto3

TABLE_NAME = "quantile-subscriptions"
AWS_REGION = "ap-south-1"

# Prices in paise (Razorpay's smallest-unit convention for INR) — same
# figures as the pricing page's own display copy (mock_data.pricing_data()),
# kept here too since this module is what actually charges them.
PLANS = {
    "free": {"name": "Free", "price_paise": 0, "period": None},
    "pro": {"name": "Pro", "price_paise": 49900, "period": "month"},
    "premium": {"name": "Premium", "price_paise": 129900, "period": "month"},
}

CAMPAIGNS_TABLE_NAME = "quantile-campaigns"

_table = None
_campaigns_table = None


class SubscriptionError(Exception):
    pass


class PartialDiscountVoucher(Exception):
    """Raised by redeem_voucher() when the code is valid but isn't a 100%
    discount — those can't activate a plan for free, they need an actual
    reduced-price charge, which is app.py's checkout-with-voucher path."""
    def __init__(self, campaign):
        self.campaign = campaign
        super().__init__(f"{campaign['percent_off']}% off — needs checkout")


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)
    return _table


def _get_campaigns_table():
    global _campaigns_table
    if _campaigns_table is None:
        _campaigns_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(CAMPAIGNS_TABLE_NAME)
    return _campaigns_table


# ============================================================
# CAMPAIGNS (admin-managed voucher codes)
# ============================================================
#
# A campaign IS a voucher code — "campaign" is the admin-facing concept
# (a named promo with a discount, e.g. "Diwali 2026 — 30% off"), "code" is
# what a subscriber types in. `active` gates whether the code can be
# redeemed at all; `visible` separately gates whether it's advertised on
# the subscriber-facing /subscription page — a campaign can be active but
# hidden (a private code shared directly with specific people, not
# publicly promoted) or visible but inactive (a promo that's ended but
# should still show as "expired" rather than just vanish, if ever needed).

def create_campaign(name, code, percent_off, applicable_plans, active, visible, max_redemptions, created_by):
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code:
        raise SubscriptionError("A voucher code is required.")
    if not name:
        raise SubscriptionError("A campaign name is required.")
    try:
        percent_off = int(percent_off)
    except (TypeError, ValueError):
        raise SubscriptionError("Discount must be a number between 1 and 100.")
    if not (1 <= percent_off <= 100):
        raise SubscriptionError("Discount must be between 1% and 100%.")

    applicable_plans = [p for p in (applicable_plans or []) if p in ("pro", "premium")]
    if not applicable_plans:
        raise SubscriptionError("Choose at least one plan this voucher applies to.")

    if get_campaign(code):
        raise SubscriptionError(f'A campaign with code "{code}" already exists.')

    now_iso = datetime.datetime.utcnow().isoformat()
    item = {
        "code": code,
        "name": name,
        "percent_off": percent_off,
        "applicable_plans": applicable_plans,
        "active": bool(active),
        "visible": bool(visible),
        "max_redemptions": int(max_redemptions) if max_redemptions else None,
        "redemption_count": 0,
        "created_by": created_by,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _get_campaigns_table().put_item(Item=item)
    return item


def list_campaigns():
    items = _get_campaigns_table().scan().get("Items", [])
    items.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return items


def list_visible_campaigns():
    """What the subscriber-facing page advertises — active AND visible."""
    return [c for c in list_campaigns() if c.get("active") and c.get("visible")]


def get_campaign(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    return _get_campaigns_table().get_item(Key={"code": code}).get("Item")


def update_campaign(code, **fields):
    existing = get_campaign(code)
    if not existing:
        raise SubscriptionError("Campaign not found.")
    item = {**existing, **fields, "code": existing["code"], "updated_at": datetime.datetime.utcnow().isoformat()}
    _get_campaigns_table().put_item(Item=item)
    return item


def delete_campaign(code):
    code = (code or "").strip().upper()
    _get_campaigns_table().delete_item(Key={"code": code})


def _increment_redemption_count(code):
    """Atomic ADD rather than read-modify-write — safe if two people redeem
    the same code at nearly the same moment."""
    _get_campaigns_table().update_item(
        Key={"code": code},
        UpdateExpression="ADD redemption_count :incr SET updated_at = :now",
        ExpressionAttributeValues={":incr": 1, ":now": datetime.datetime.utcnow().isoformat()},
    )


def check_campaign_eligibility(code, plan_id):
    """Shared validation between the direct-redeem (100% off) and the
    checkout-with-discount (<100% off) paths. Returns the campaign dict, or
    raises SubscriptionError with a message safe to show the subscriber."""
    campaign = get_campaign(code)
    if not campaign or not campaign.get("active"):
        raise SubscriptionError("That voucher code isn't valid.")
    if plan_id not in (campaign.get("applicable_plans") or []):
        raise SubscriptionError(f"This voucher isn't valid for the {PLANS[plan_id]['name']} plan.")
    max_redemptions = campaign.get("max_redemptions")
    if max_redemptions is not None and campaign.get("redemption_count", 0) >= max_redemptions:
        raise SubscriptionError("This voucher has reached its redemption limit.")
    return campaign


def _default_record(email):
    return {
        "email": email,
        "plan": "free",
        "status": "active",
        "razorpay_subscription_id": None,
        "razorpay_customer_id": None,
        "current_period_end": None,
        "voucher_code": None,
        "created_at": None,
        "updated_at": None,
        "history": [],
    }


def _apply_lazy_expiry(item):
    """A canceled record whose period end has passed, with nothing renewing
    it (no cron job in this phase), reads back as a plain active Free plan
    rather than a stale "canceled Pro" — shared by every reader (single
    lookup and admin list/stats) so they can't disagree with each other."""
    item = dict(item)
    now_iso = datetime.datetime.utcnow().isoformat()
    if item["status"] == "canceled" and item.get("current_period_end") and now_iso > item["current_period_end"]:
        item["plan"] = "free"
        item["status"] = "active"
        item["razorpay_subscription_id"] = None
    return item


def get_subscription(email):
    response = _get_table().get_item(Key={"email": email})
    item = _apply_lazy_expiry(response.get("Item") or _default_record(email))
    item["plan_details"] = PLANS[item["plan"]]
    return item


def list_all_subscriptions():
    """Every row in quantile-subscriptions, with lazy expiry applied — the
    admin console's real subscriptions list. Only accounts with subscription
    history have a row at all (see _default_record() — everyone else is an
    implicit, unwritten Free record), so this is "everyone who's ever
    subscribed or redeemed a voucher", not literally every user."""
    items = [_apply_lazy_expiry(item) for item in _get_table().scan().get("Items", [])]
    items.sort(key=lambda i: i.get("updated_at") or "", reverse=True)
    return items


def get_plans_for_emails(emails):
    """Bulk plan lookup for a list of emails — one table scan rather than
    one get_subscription() get_item call per user, for the admin
    campaign builder's audience (Free/Pro/Premium) filtering. Anyone with
    no subscription row is an implicit Free user (see _default_record),
    same rule get_subscription() applies for a single lookup."""
    rows = {s["email"]: s["plan"] for s in list_all_subscriptions()}
    return {email: rows.get(email, "free") for email in emails}


def compute_revenue_stats(total_user_count):
    """Real MRR + plan mix, computed from actual subscription records —
    there's no historical time series stored anywhere (only current state),
    so this is a snapshot, not a trend; the admin overview page shows it as
    one, not as a month-over-month chart it can't honestly draw."""
    records = list_all_subscriptions()
    mrr_paise = 0
    paid_counts = {"pro": 0, "premium": 0}
    for item in records:
        if item["status"] == "active" and item["plan"] in ("pro", "premium"):
            mrr_paise += PLANS[item["plan"]]["price_paise"]
            paid_counts[item["plan"]] += 1

    free_count = max(total_user_count - paid_counts["pro"] - paid_counts["premium"], 0)
    return {
        "mrr_paise": mrr_paise,
        "plan_counts": {"free": free_count, "pro": paid_counts["pro"], "premium": paid_counts["premium"]},
        "total_users": total_user_count,
    }


def _save(email, event, **fields):
    existing = get_subscription(email)
    now_iso = datetime.datetime.utcnow().isoformat()

    item = {**existing, **fields, "email": email, "updated_at": now_iso}
    item.pop("plan_details", None)  # derived, not stored
    item.setdefault("created_at", now_iso)
    if item.get("created_at") is None:
        item["created_at"] = now_iso

    history = list(existing.get("history") or [])
    history.append({"event": event, "at": now_iso, "plan": item["plan"], "status": item["status"]})
    item["history"] = history[-20:]  # cap — this is a status trail, not an audit log

    _get_table().put_item(Item=item)
    return get_subscription(email)


def redeem_voucher(email, plan_id, code):
    """The "skip payment" path — only for 100%-off codes: activates the
    plan directly against our own record, with no Razorpay call at all
    (you can't create a zero-amount order on Razorpay's side, so there's
    nothing for the gateway to do here). A <100% voucher is valid but
    can't be redeemed this way — it needs an actual reduced-price charge,
    which only checkout (create_discounted_checkout) can do."""
    if plan_id not in PLANS or plan_id == "free":
        raise SubscriptionError("Choose a paid plan to apply a voucher to.")

    campaign = check_campaign_eligibility(code, plan_id)
    if campaign["percent_off"] < 100:
        raise PartialDiscountVoucher(campaign)

    period_end = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()
    sub = _save(
        email, "voucher_redeemed",
        plan=plan_id, status="active", voucher_code=campaign["code"],
        current_period_end=period_end, razorpay_subscription_id=None,
    )
    _increment_redemption_count(campaign["code"])
    return sub


def apply_razorpay_subscription(email, plan_id, razorpay_subscription_id, razorpay_customer_id, current_period_end, voucher_code=None):
    """Called once a real Razorpay subscription is confirmed active
    (either synchronously after checkout, or from the subscription.activated
    webhook — whichever fires first; the other becomes a no-op re-save)."""
    return _save(
        email, "subscription_activated",
        plan=plan_id, status="active", voucher_code=voucher_code,
        razorpay_subscription_id=razorpay_subscription_id,
        razorpay_customer_id=razorpay_customer_id,
        current_period_end=current_period_end,
    )


def record_voucher_redemption(code):
    """Public wrapper so app.py can credit a partial-discount voucher's
    redemption count once checkout actually confirms (rather than at
    checkout-start, before payment is verified)."""
    campaign = get_campaign(code)
    if campaign:
        _increment_redemption_count(campaign["code"])


def cancel_subscription(email):
    sub = get_subscription(email)
    if sub["plan"] == "free":
        raise SubscriptionError("You're already on the Free plan — there's nothing to cancel.")
    return _save(email, "canceled", status="canceled")


def mark_past_due(email):
    """A renewal charge failed (subscription.charged with a failed payment,
    or subscription.halted) — Razorpay's own retry schedule handles retries;
    this just reflects that state so the UI can show it."""
    return _save(email, "past_due", status="past_due")
