"""Hand-off table between Quantile's breakout-race winner (app.py's
_breakout_watch_once) and trading-bot-algo's dedicated-IP order executor.

One table, quantile-order-intents, keyed by entry_id (the campaign
entry's own id, so it's naturally unique per trade — no separate id
needed). Two conditional writes are the idempotency gates that make the
whole auto-order pipeline safe against duplicate triggers (the same
failure mode that caused real duplicate push notifications on
2026-09-21 when repeated backend restarts re-ran the breakout picker):

  1. create_intent() — ConditionExpression=attribute_not_exists(entry_id)
     on the Quantile side, so a _breakout_watch_once() re-run for the
     same entry can never enqueue a second order intent.
  2. claim_intent() — ConditionExpression=status is still "pending" on
     the trading-bot-algo side, so two overlapping poll cycles (or a
     poller that starts twice) can never both act on the same intent.

status progresses: pending -> claimed -> paper_filled | live_filled -> closed
"""

import datetime

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from decimal import Decimal, InvalidOperation

AWS_REGION = "ap-south-1"
ORDER_TRIGGER_LAMBDA = "quantile-order-trigger"

_intents_table = None
_lambda_client = None


class OrderIntentError(Exception):
    pass


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    return _lambda_client


def trigger_order_executor():
    """Fire-and-forget invoke of the dedicated-IP order executor's
    launcher Lambda — asynchronous (InvocationType="Event") so a slow
    EC2 launch can never block app.py's fast (60s-cadence)
    _breakout_watch_once() loop. Failure here is logged, not raised —
    the order intent row itself is already durably written by
    create_intent() by the time this is called, so a transient Lambda
    invoke failure doesn't lose the order, it just delays pickup until
    someone/something else notices the still-pending row."""
    try:
        _get_lambda_client().invoke(FunctionName=ORDER_TRIGGER_LAMBDA, InvocationType="Event")
    except Exception as exc:
        raise OrderIntentError(f"couldn't trigger order executor: {exc}")


def _get_intents_table():
    global _intents_table
    if _intents_table is None:
        _intents_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table("quantile-order-intents")
    return _intents_table


def _to_decimal(value, field_name):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise OrderIntentError(f"{field_name} must be a number.")


def create_intent(entry_id, symbol, security_id, side, entry_price, sl_price, target_price=None):
    """Idempotency gate 1. Returns the created item, or None if an intent
    for this entry_id already exists (never raises for that case — a
    duplicate _breakout_watch_once() run should just no-op silently, not
    break the caller)."""
    now_iso = datetime.datetime.utcnow().isoformat()
    item = {
        "entry_id": entry_id,
        "symbol": (symbol or "").strip().upper(),
        "security_id": str(security_id),
        "side": (side or "BUY").strip().upper(),
        "entry_price": _to_decimal(entry_price, "Entry price"),
        "sl_price": _to_decimal(sl_price, "Stop-loss price"),
        "target_price": _to_decimal(target_price, "Target price"),
        "status": "pending",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    try:
        _get_intents_table().put_item(
            Item=item,
            ConditionExpression=Attr("entry_id").not_exists(),
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise
    return item


def claim_intent(entry_id):
    """Idempotency gate 2. Returns the claimed item, or None if it's
    already claimed/past pending (by this or another poll cycle)."""
    now_iso = datetime.datetime.utcnow().isoformat()
    try:
        result = _get_intents_table().update_item(
            Key={"entry_id": entry_id},
            UpdateExpression="SET #s = :claimed, updated_at = :now",
            ConditionExpression=Attr("status").eq("pending"),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":claimed": "claimed", ":now": now_iso},
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise
    return result.get("Attributes")


def get_intent(entry_id):
    return _get_intents_table().get_item(Key={"entry_id": entry_id}).get("Item")


def update_intent(entry_id, **fields):
    existing = get_intent(entry_id)
    if not existing:
        raise OrderIntentError("Order intent not found.")
    for price_field in ("entry_price", "sl_price", "target_price", "filled_qty", "risk_amount"):
        if price_field in fields:
            fields[price_field] = _to_decimal(fields[price_field], price_field)
    item = {**existing, **fields, "entry_id": entry_id, "updated_at": datetime.datetime.utcnow().isoformat()}
    _get_intents_table().put_item(Item=item)
    return item


def list_pending_intents():
    items = _get_intents_table().scan(
        FilterExpression=Attr("status").eq("pending"),
    ).get("Items", [])
    items.sort(key=lambda i: i.get("created_at") or "")
    return items


def list_open_intents():
    """claimed/paper_filled/live_filled — anything not yet closed. Used by
    trading-bot-algo's self-termination check so it never shuts down
    while a trade it placed is still open."""
    items = _get_intents_table().scan(
        FilterExpression=Attr("status").is_in(["claimed", "paper_filled", "live_filled"]),
    ).get("Items", [])
    return items


def list_all_intents():
    """Every intent, newest first — for the admin Quantile Orders page.
    A plain paginated scan: this table only grows by one row per
    breakout-race winner, so it stays small."""
    table = _get_intents_table()
    kwargs = {}
    items = []
    while True:
        page = table.scan(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return items


def save_dhan_snapshot(entry_id, snapshot):
    """Persist the last-seen Dhan super order state onto the intent row.
    Dhan's super order book only covers the current trading day, so
    without this a closed trade's exit price/reason would vanish from
    the admin page the next morning. A targeted SET (not update_intent's
    get+put) so it can never clobber a status write trading-bot-algo
    makes at the same moment."""
    _get_intents_table().update_item(
        Key={"entry_id": entry_id},
        UpdateExpression="SET dhan_snapshot = :s",
        ExpressionAttributeValues={":s": snapshot},
    )
