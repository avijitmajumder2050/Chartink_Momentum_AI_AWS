"""Admin scanner-campaign data — trade-idea entries (symbol + entry/stop-
loss/target price, sourced from a scanner match or added manually), the
notification log, and reusable message templates, all in DynamoDB.

Four tables:
  quantile-campaign-entries    — the trade ideas themselves
  quantile-notifications       — every campaign actually sent; doubles as
                                  the in-app notification feed every
                                  signed-in user reads from (GET
                                  /api/notifications/recent) AND the
                                  admin's send history — one send is one
                                  broadcast to everyone, so one row serves
                                  both purposes without duplicating data.
  quantile-push-tokens         — browser FCM registration tokens, keyed by
                                  token (not email) since one person can
                                  have several devices/browsers each with
                                  their own token.
  quantile-campaign-templates  — named, reusable Title/Header/Entry-line/
                                  Footer combos the admin has saved (e.g.
                                  one for momentum alerts, one for swing,
                                  one for a calmer educational tone),
                                  loadable from a dropdown in the campaign
                                  builder instead of retyping every time.
"""

import datetime
import uuid
from decimal import Decimal, InvalidOperation

import boto3

AWS_REGION = "ap-south-1"

_entries_table = None
_notifications_table = None
_push_tokens_table = None
_templates_table = None


class CampaignError(Exception):
    pass


def _get_entries_table():
    global _entries_table
    if _entries_table is None:
        _entries_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("quantile-campaign-entries")
    return _entries_table


def _get_notifications_table():
    global _notifications_table
    if _notifications_table is None:
        _notifications_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("quantile-notifications")
    return _notifications_table


def _get_push_tokens_table():
    global _push_tokens_table
    if _push_tokens_table is None:
        _push_tokens_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("quantile-push-tokens")
    return _push_tokens_table


def _get_templates_table():
    global _templates_table
    if _templates_table is None:
        _templates_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("quantile-campaign-templates")
    return _templates_table


# ============================================================
# CAMPAIGN ENTRIES
# ============================================================

def _to_decimal(value, field_name):
    # DynamoDB's boto3 resource rejects plain Python float outright ("Float
    # types are not supported. Use Decimal types instead.") — going through
    # str() first avoids binary-float rounding artifacts (Decimal(0.1) !=
    # Decimal("0.1")).
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise CampaignError(f"{field_name} must be a number.")


ENTRY_TYPES = ("momentum", "swing")


def _clean_entry_type(entry_type):
    entry_type = (entry_type or "").strip().lower()
    if entry_type and entry_type not in ENTRY_TYPES:
        raise CampaignError("Type must be Momentum or Swing.")
    return entry_type


def create_entry(symbol, entry_price, sl_price, target_price, note, source, created_by, entry_type=""):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise CampaignError("A stock symbol is required.")

    now_iso = datetime.datetime.utcnow().isoformat()
    item = {
        "id": uuid.uuid4().hex,
        "symbol": symbol,
        "entry_price": _to_decimal(entry_price, "Entry price"),
        "sl_price": _to_decimal(sl_price, "Stop-loss price"),
        "target_price": _to_decimal(target_price, "Target price"),
        "note": (note or "").strip(),
        "source": source or "manual",
        "type": _clean_entry_type(entry_type),
        "active": True,
        # Which of the alert-tracking bot's milestones (entry_triggered,
        # profit_2pct, rr_1_1, rr_1_2 — see app.py's ALERT_MILESTONES)
        # have already fired a notification for this entry, so the bot
        # never re-notifies the same milestone twice.
        "milestones_notified": [],
        "created_by": created_by,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _get_entries_table().put_item(Item=item)
    return item


def list_entries(active_only=False):
    items = _get_entries_table().scan().get("Items", [])
    if active_only:
        items = [i for i in items if i.get("active")]
    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return items


def get_entry(entry_id):
    return _get_entries_table().get_item(Key={"id": entry_id}).get("Item")


def update_entry(entry_id, **fields):
    existing = get_entry(entry_id)
    if not existing:
        raise CampaignError("Entry not found.")
    for price_field in ("entry_price", "sl_price", "target_price"):
        if price_field in fields:
            fields[price_field] = _to_decimal(fields[price_field], price_field)
    if "type" in fields:
        fields["type"] = _clean_entry_type(fields["type"])
    item = {**existing, **fields, "id": entry_id, "updated_at": datetime.datetime.utcnow().isoformat()}
    _get_entries_table().put_item(Item=item)
    return item


def delete_entry(entry_id):
    _get_entries_table().delete_item(Key={"id": entry_id})


# ============================================================
# NOTIFICATIONS (send log + in-app feed, same table)
# ============================================================

def record_notification(title, body, entry_symbols, channels, recipient_count, sent_by, audience=None):
    now_iso = datetime.datetime.utcnow().isoformat()
    item = {
        "id": uuid.uuid4().hex,
        "title": title,
        "body": body,
        "entry_symbols": entry_symbols or [],
        "channels": channels,
        "audience": audience or ["free", "pro", "premium"],
        "recipient_count": recipient_count,
        "sent_by": sent_by,
        "sent_at": now_iso,
    }
    _get_notifications_table().put_item(Item=item)
    return item


def list_recent_notifications(limit=20):
    items = _get_notifications_table().scan().get("Items", [])
    items.sort(key=lambda i: i.get("sent_at") or "", reverse=True)
    return items[:limit]


def delete_notification(notification_id):
    """Removes one sent campaign from quantile-notifications — since that
    table doubles as every signed-in subscriber's in-app notification feed
    (GET /api/notifications/recent), deleting here also removes it from
    subscribers' notification inbox, not just the admin's send history."""
    _get_notifications_table().delete_item(Key={"id": notification_id})


def delete_notifications(notification_ids):
    """Bulk version of delete_notification, for the admin's "Delete
    selected" action — DynamoDB's Table resource has no batch-delete
    helper, so this is just delete_item per id, one request each."""
    table = _get_notifications_table()
    for notification_id in notification_ids:
        table.delete_item(Key={"id": notification_id})


# ============================================================
# CAMPAIGN TEMPLATES (saved Title/Header/Entry-line/Footer combos)
# ============================================================

def create_template(name, title, header, entry_line_template, footer, created_by):
    name = (name or "").strip()
    if not name:
        raise CampaignError("A template name is required.")

    now_iso = datetime.datetime.utcnow().isoformat()
    item = {
        "id": uuid.uuid4().hex,
        "name": name,
        "title": (title or "").strip(),
        "header": (header or "").strip(),
        "entry_line_template": (entry_line_template or "").strip(),
        "footer": (footer or "").strip(),
        "created_by": created_by,
        "created_at": now_iso,
    }
    _get_templates_table().put_item(Item=item)
    return item


def list_templates():
    items = _get_templates_table().scan().get("Items", [])
    items.sort(key=lambda i: i.get("name", "").lower())
    return items


def delete_template(template_id):
    _get_templates_table().delete_item(Key={"id": template_id})


# ============================================================
# PUSH TOKENS
# ============================================================

def register_push_token(token, email):
    _get_push_tokens_table().put_item(Item={
        "token": token,
        "email": email,
        "updated_at": datetime.datetime.utcnow().isoformat(),
    })


def remove_push_token(token):
    _get_push_tokens_table().delete_item(Key={"token": token})


def list_all_push_tokens():
    return [i["token"] for i in _get_push_tokens_table().scan().get("Items", [])]


def list_push_tokens_for_emails(emails):
    """Push tokens belonging only to the given emails — for the admin
    campaign builder's audience (Free/Pro/Premium) filtering, so a
    Pro/Premium-only send doesn't push to Free subscribers' devices."""
    emails = set(emails)
    return [i["token"] for i in _get_push_tokens_table().scan().get("Items", []) if i.get("email") in emails]
