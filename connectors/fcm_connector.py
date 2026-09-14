"""Firebase Cloud Messaging — free push notifications, chosen specifically
because it needs no Telegram channel and no AWS SES sandbox/production-
access wait (SES only lets a new account email addresses you've verified
one-by-one until AWS approves going live; FCM has no such gate).

Sends via FCM's HTTP v1 REST API directly (requests + google-auth for
minting an OAuth2 access token from a service-account key) rather than the
full firebase-admin SDK — that SDK pulls in google-cloud-firestore and a
deep protobuf dependency tree that risks the same Windows MAX_PATH
pip-install failure this project already hit once (see the .venv note in
connectors/secrets.py's neighbors). google-auth alone is much lighter and
is all the REST API actually needs.

Setup (blocked on the user providing these — nothing here can be created
by AWS CLI, it's a separate Google/Firebase project):
  1. Create a Firebase project at console.firebase.google.com (free).
  2. Project Settings -> Service Accounts -> Generate new private key ->
     downloads a JSON file. Store its whole contents as one SSM SecureString:
       /chartink-momentum-ai/fcm/service_account_json
  3. Project Settings -> Cloud Messaging -> Web Push certificates -> generate
     a key pair. The public VAPID key + the web app's Firebase config
     (apiKey/projectId/messagingSenderId/appId — all public, safe to embed
     in frontend JS) go into SSM as plain Strings for the notification-bell
     opt-in flow to use:
       /chartink-momentum-ai/fcm/vapid_public_key
       /chartink-momentum-ai/fcm/web_config_json
"""

import json
import sys

import requests

try:
    from google.oauth2 import service_account
    import google.auth.transport.requests as google_auth_transport
except ImportError:
    service_account = None
    google_auth_transport = None

from connectors import secrets

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

_configured = None
_credentials = None
_project_id = None


def is_configured():
    global _configured
    if _configured is None:
        try:
            secrets.get_parameter("/chartink-momentum-ai/fcm/service_account_json")
            _configured = service_account is not None
        except Exception:
            _configured = False
    return _configured


def _get_credentials():
    global _credentials, _project_id
    if service_account is None:
        raise RuntimeError("google-auth is not installed")
    if _credentials is None:
        raw = secrets.get_parameter("/chartink-momentum-ai/fcm/service_account_json")
        info = json.loads(raw)
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=[FCM_SCOPE])
        _project_id = info["project_id"]
    return _credentials


def _access_token():
    creds = _get_credentials()
    if not creds.valid:
        creds.refresh(google_auth_transport.Request())
    return creds.token


def send_to_token(token, title, body, data=None):
    """One push to one device token. `data` (optional dict of string
    values) rides alongside the visible notification, invisible to the
    user — used for things like a click-target URL the service worker
    reads on notificationclick, kept OUT of the visible body text (e.g.
    the campaign builder's "View Chart" CTA shows a clean label, not a raw
    URL, because the URL travels here instead of in `body`).

    Returns True on success, False if the token is invalid/unregistered
    (caller should drop it from storage — see
    connectors/campaign_connector.py's push-token table), raises on any
    other error (auth failure, FCM outage, etc.)."""
    _get_credentials()  # ensures _project_id is populated
    url = f"https://fcm.googleapis.com/v1/projects/{_project_id}/messages:send"
    message = {"token": token, "notification": {"title": title, "body": body}}
    if data:
        message["data"] = {str(k): str(v) for k, v in data.items()}
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
        json={"message": message},
        timeout=15,
    )
    if response.status_code == 200:
        return True
    error = (response.json() or {}).get("error", {})
    if error.get("status") in ("NOT_FOUND", "UNREGISTERED", "INVALID_ARGUMENT"):
        return False
    raise RuntimeError(f"FCM send failed ({response.status_code}): {error}")


def send_to_tokens(tokens, title, body, data=None):
    """FCM's v1 API has no true multicast endpoint (unlike the deprecated
    legacy API), so this sends one request per token — fine at this app's
    scale. Returns (sent_count, stale_tokens) so the caller can prune dead
    registrations rather than retrying them forever."""
    sent = 0
    stale = []
    for token in tokens:
        try:
            if send_to_token(token, title, body, data=data):
                sent += 1
            else:
                stale.append(token)
        except Exception as exc:
            # One bad/expired token shouldn't abort the whole campaign, but a
            # silent `continue` here previously meant a real failure (bad
            # credentials, FCM outage, misconfigured project) looked
            # identical to "0 devices subscribed" with nothing in the logs
            # to tell them apart — print so it shows up in the server console.
            print(f"[fcm_connector] send_to_token failed for a token: {exc}", file=sys.stderr)
            continue
    return sent, stale
