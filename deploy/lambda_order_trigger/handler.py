"""Launches trading-bot-algo's dedicated-IP EC2 instance (if one isn't
already up) so it can pick up a pending row from Quantile's
quantile-order-intents DynamoDB table and place the real Dhan order.

Invoked directly (InvocationType="Event", fire-and-forget) by
app.py's _breakout_watch_once() the moment a breakout race winner is
declared and its order intent has been written — see
connectors/order_intent_connector.py for the two-gate idempotency
design this hands off into.

Deliberately does nothing else: it doesn't know about order intents,
position sizing, or Dhan at all — trading-bot-algo's own app polls
quantile-order-intents itself once it's up (see its
app/bot/scheduler.py). This function's only job is "make sure the
dedicated-IP instance is running", same shape as
quantile-backend-scheduler's _start(), just for a different instance
and without any CloudFront origin-update step (this instance has a
fixed Elastic IP, so nothing downstream needs to know its address).
"""

import boto3

REGION = "ap-south-1"
# The dedicated launch template for this project (lt-0bd1e940d7668cdee) -
# NOT the similarly-named "trading-bot" template, which belongs to a
# separate, unrelated project (its own Telegram bot + insidebar/
# opposite-15m scanner strategies, github.com/avijitmajumder2050/
# trading-bot). Confirmed via its own app/utils/ec2_launcher.py, which
# already expected a dedicated /trading-bot-algo/ec2/launch_template_id
# SSM param pointing at this exact template - this project's proper
# infra was already built, just never wired up before today.
LAUNCH_TEMPLATE_NAME = "trading-bot-algo"
NAME_TAG_VALUE = "trading-bot-algo"

ec2 = boto3.client("ec2", region_name=REGION)


def _running_or_pending_instance_id():
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [NAME_TAG_VALUE]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ]
    )
    for reservation in resp["Reservations"]:
        for instance in reservation["Instances"]:
            return instance["InstanceId"]
    return None


def handler(event, context):
    existing = _running_or_pending_instance_id()
    if existing:
        return {"status": "already_running", "instanceId": existing}

    resp = ec2.run_instances(
        LaunchTemplate={"LaunchTemplateName": LAUNCH_TEMPLATE_NAME, "Version": "$Latest"},
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": NAME_TAG_VALUE}]}
        ],
    )
    instance_id = resp["Instances"][0]["InstanceId"]
    return {"status": "launched", "instanceId": instance_id}
