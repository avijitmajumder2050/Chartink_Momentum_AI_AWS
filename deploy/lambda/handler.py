"""Start/stop the Quantile staging backend EC2 instance, keeping
CloudFront's origin pointed at whatever public DNS the instance gets
on each start (it has no Elastic IP, so that DNS changes every
stop -> start). Invoked either by EventBridge Scheduler (the 9/11 IST
weekday schedules, event = {"action": "start"|"stop"}) or via API
Gateway (REST API, not HTTP API - see deploy/README.md for why) from
deploy/ondemand.html (action passed as a query string param or JSON
body, same shape).

Not a real access-control mechanism - the shared secret this checks
is necessarily visible in ondemand.html's own JS source to anyone who
loads the page. It exists only to stop an accidental/drive-by trigger
of billable infrastructure, not a determined visitor.
"""

import json
import time

import boto3

REGION = "ap-south-1"
INSTANCE_ID = "i-035c10ae55c3f8b9c"
DISTRIBUTION_ID = "E3SG9FAP3WCJBZ"
EC2_ORIGIN_ID = "ec2-backend"
TRIGGER_KEY_PARAM = "/chartink-momentum-ai/scheduler_trigger_key"

ec2 = boto3.client("ec2", region_name=REGION)
cloudfront = boto3.client("cloudfront", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)

_trigger_key_cache = None


def _expected_trigger_key():
    global _trigger_key_cache
    if _trigger_key_cache is None:
        _trigger_key_cache = ssm.get_parameter(Name=TRIGGER_KEY_PARAM, WithDecryption=True)["Parameter"]["Value"]
    return _trigger_key_cache


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://dz1fb1xrtg7b3.cloudfront.net",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "content-type,x-trigger-key",
}


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **CORS_HEADERS},
        "body": json.dumps(body),
    }


def _describe():
    resp = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    instance = resp["Reservations"][0]["Instances"][0]
    return {
        "state": instance["State"]["Name"],
        "publicDns": instance.get("PublicDnsName") or None,
    }


def _update_cloudfront_origin(new_domain):
    current = cloudfront.get_distribution_config(Id=DISTRIBUTION_ID)
    etag = current["ETag"]
    config = current["DistributionConfig"]

    origins = config["Origins"]["Items"]
    origin = next((o for o in origins if o["Id"] == EC2_ORIGIN_ID), None)
    if origin is None:
        raise RuntimeError(f"origin {EC2_ORIGIN_ID!r} not found in distribution {DISTRIBUTION_ID}")

    if origin["DomainName"] == new_domain:
        return False  # already correct, no update needed

    origin["DomainName"] = new_domain
    cloudfront.update_distribution(Id=DISTRIBUTION_ID, IfMatch=etag, DistributionConfig=config)
    return True


def _start():
    state = _describe()
    if state["state"] not in ("stopped", "stopping"):
        # already running (or on its way there) - just make sure CloudFront agrees
        if state["publicDns"]:
            updated = _update_cloudfront_origin(state["publicDns"])
            return {"status": state["state"], "publicDns": state["publicDns"], "cloudfrontUpdating": updated}
        return {"status": state["state"], "publicDns": None, "cloudfrontUpdating": False}

    ec2.start_instances(InstanceIds=[INSTANCE_ID])

    deadline = time.time() + 90
    public_dns = None
    while time.time() < deadline:
        state = _describe()
        if state["state"] == "running" and state["publicDns"]:
            public_dns = state["publicDns"]
            break
        time.sleep(5)

    if not public_dns:
        return {"status": "starting", "publicDns": None, "cloudfrontUpdating": False, "note": "instance not fully up yet, CloudFront not updated - retry status shortly"}

    updated = _update_cloudfront_origin(public_dns)
    return {"status": "running", "publicDns": public_dns, "cloudfrontUpdating": updated}


def _stop():
    ec2.stop_instances(InstanceIds=[INSTANCE_ID])
    return {"status": "stopping"}


def handler(event, context):
    # REST API (AWS_PROXY) sends the browser's CORS preflight straight
    # through to the function too (unlike an HTTP API, which can answer
    # OPTIONS itself) - answer it directly, no trigger-key check, no
    # actual work done.
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # REST API proxy event: headers as given (case varies by client),
    # query params under queryStringParameters. Support both a query
    # param and a JSON body so EventBridge Scheduler's plain
    # {"action": "..."} event also works with no HTTP envelope at all.
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    query = event.get("queryStringParameters") or {}

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (TypeError, ValueError):
            body = {}

    action = event.get("action") or body.get("action") or query.get("action")

    # EventBridge Scheduler invokes the function directly (no HTTP
    # envelope, no headers) - only enforce the trigger key for HTTP
    # (API Gateway) calls, which is the only path a browser can reach.
    is_http_call = "requestContext" in event
    if is_http_call:
        provided_key = headers.get("x-trigger-key") or query.get("key")
        if provided_key != _expected_trigger_key():
            return _response(403, {"error": "invalid or missing trigger key"})

    try:
        if action == "start":
            result = _start()
        elif action == "stop":
            result = _stop()
        elif action == "status":
            result = _describe()
        else:
            return _response(400, {"error": f"unknown action: {action!r}"})
    except Exception as exc:
        return _response(500, {"error": str(exc)})

    return _response(200, result)
