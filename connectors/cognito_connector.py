"""AWS Cognito connector — real email/password auth backing the login page.

User Pool + App Client were created once via the AWS CLI (see the project's
own notes; pool "quantile-users" in ap-south-1) and their IDs/secret live in
SSM Parameter Store under /chartink-momentum-ai/cognito/*, same pattern as
every other credential this project pulls from Parameter Store
(connectors/secrets.py).

The App Client has a secret (it's only ever called from this Flask backend,
never from a browser directly), so every Cognito call below must include a
SECRET_HASH — HMAC-SHA256(client_secret, username + client_id), base64
encoded, exactly as Cognito's docs specify.

Every public function raises AuthError(message) with a message that's
already safe to show a user directly (not a raw AWS error) on failure, and
returns plain dicts (never botocore response objects) on success — app.py's
routes don't need to know anything about boto3.
"""

import base64
import hashlib
import hmac
import json

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from connectors import secrets

CONFIG_CACHE_TTL_SECONDS = 24 * 60 * 60

_client = None
_config = None

# Cognito's own exception codes -> a message safe to show the user.
_ERROR_MESSAGES = {
    "UsernameExistsException": "An account with this email already exists.",
    "UserNotFoundException": "No account found with this email.",
    "NotAuthorizedException": "Incorrect email or password.",
    "UserNotConfirmedException": "Please verify your email before logging in.",
    "CodeMismatchException": "That verification code is incorrect.",
    "ExpiredCodeException": "That verification code has expired — request a new one.",
    "InvalidPasswordException": "Password must be at least 8 characters, with an uppercase letter, a lowercase letter, and a number.",
    "InvalidParameterException": "Please check the details you entered.",
    "LimitExceededException": "Too many attempts — please wait a moment and try again.",
    "TooManyRequestsException": "Too many attempts — please wait a moment and try again.",
    "AliasExistsException": "An account with this email already exists.",
}


class AuthError(Exception):
    pass


def _raise_friendly(exc):
    code = exc.response.get("Error", {}).get("Code", "")
    raise AuthError(_ERROR_MESSAGES.get(code, "Something went wrong — please try again."))


def _get_config():
    global _config
    if _config is None:
        _config = {
            "user_pool_id": secrets.get_parameter("/chartink-momentum-ai/cognito/user_pool_id"),
            "client_id": secrets.get_parameter("/chartink-momentum-ai/cognito/client_id"),
            "client_secret": secrets.get_parameter("/chartink-momentum-ai/cognito/client_secret"),
            "region": secrets.get_parameter("/chartink-momentum-ai/cognito/region"),
        }
    return _config


def _get_client():
    global _client
    if boto3 is None:
        raise RuntimeError("boto3 is not installed")
    if _client is None:
        _client = boto3.client("cognito-idp", region_name=_get_config()["region"])
    return _client


def _secret_hash(username):
    config = _get_config()
    message = (username + config["client_id"]).encode("utf-8")
    key = config["client_secret"].encode("utf-8")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def sign_up(email, password, name):
    """Registers a new (unconfirmed) user. Cognito emails a 6-digit code to
    `email`; the account can't sign in until confirm_sign_up() succeeds.
    `name` is stored on Cognito's standard "name" attribute and comes back
    as a claim in every ID token this user is issued (see decode_claims())."""
    config = _get_config()
    try:
        _get_client().sign_up(
            ClientId=config["client_id"],
            SecretHash=_secret_hash(email),
            Username=email,
            Password=password,
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "name", "Value": name}],
        )
    except ClientError as exc:
        _raise_friendly(exc)


def confirm_sign_up(email, code):
    config = _get_config()
    try:
        _get_client().confirm_sign_up(
            ClientId=config["client_id"],
            SecretHash=_secret_hash(email),
            Username=email,
            ConfirmationCode=code,
        )
    except ClientError as exc:
        _raise_friendly(exc)


def resend_confirmation_code(email):
    config = _get_config()
    try:
        _get_client().resend_confirmation_code(
            ClientId=config["client_id"],
            SecretHash=_secret_hash(email),
            Username=email,
        )
    except ClientError as exc:
        _raise_friendly(exc)


def _tokens_from_auth_result(result):
    return {
        "id_token": result["IdToken"],
        "access_token": result["AccessToken"],
        "refresh_token": result.get("RefreshToken"),  # absent on a refresh-flow call
        "expires_in": result["ExpiresIn"],
    }


def sign_in(email, password):
    """Returns {id_token, access_token, refresh_token, expires_in} on
    success. Raises AuthError (with UserNotConfirmedException mapped to a
    "please verify your email" message) on failure."""
    config = _get_config()
    try:
        response = _get_client().initiate_auth(
            ClientId=config["client_id"],
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": password,
                "SECRET_HASH": _secret_hash(email),
            },
        )
    except ClientError as exc:
        _raise_friendly(exc)

    if "ChallengeName" in response:
        # Self-signup users never hit a challenge (no admin-set temp
        # passwords in this flow) — surfaced as an error rather than silently
        # mishandled if Cognito ever asks for one.
        raise AuthError("This account needs a password reset — use 'Forgot password'.")

    return _tokens_from_auth_result(response["AuthenticationResult"])


def refresh_tokens(refresh_token, email):
    """Re-issues id/access tokens from a still-valid refresh token. `email`
    is needed only to recompute SECRET_HASH — Cognito requires it on every
    call from an app client that has a secret, refresh included."""
    config = _get_config()
    try:
        response = _get_client().initiate_auth(
            ClientId=config["client_id"],
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={
                "REFRESH_TOKEN": refresh_token,
                "SECRET_HASH": _secret_hash(email),
            },
        )
    except ClientError as exc:
        _raise_friendly(exc)

    return _tokens_from_auth_result(response["AuthenticationResult"])


def get_user(access_token):
    """Live round-trip to Cognito to fetch the current user's attributes —
    also doubles as token validation (an expired/revoked access_token raises
    NotAuthorizedException here), so callers don't need to verify the JWT
    themselves."""
    try:
        response = _get_client().get_user(AccessToken=access_token)
    except ClientError as exc:
        _raise_friendly(exc)

    attributes = {a["Name"]: a["Value"] for a in response["UserAttributes"]}
    return {"email": attributes.get("email", response["Username"]), "username": response["Username"]}


def global_sign_out(access_token):
    try:
        _get_client().global_sign_out(AccessToken=access_token)
    except ClientError:
        pass  # already-expired/invalid token — logging out is a no-op either way


def forgot_password(email):
    config = _get_config()
    try:
        _get_client().forgot_password(
            ClientId=config["client_id"],
            SecretHash=_secret_hash(email),
            Username=email,
        )
    except ClientError as exc:
        _raise_friendly(exc)


def get_account_created_at(email):
    """Real account-creation timestamp from Cognito (admin API, using this
    backend's own AWS credentials — not the user's access token), for the
    dashboard's "Member since" field. Returns a datetime."""
    config = _get_config()
    try:
        response = _get_client().admin_get_user(UserPoolId=config["user_pool_id"], Username=email)
    except ClientError as exc:
        _raise_friendly(exc)
    return response["UserCreateDate"]


def list_all_users():
    """Every Cognito user with their real role — the admin console's user
    list. Role comes from one list_users_in_group("admin") call rather than
    an admin_list_groups_for_user call per user, so this stays 2 API calls
    total regardless of how many users exist, not N+1."""
    config = _get_config()
    client = _get_client()

    admin_group = client.list_users_in_group(UserPoolId=config["user_pool_id"], GroupName="admin")
    admin_emails = set()
    for user in admin_group.get("Users", []):
        attrs = {a["Name"]: a["Value"] for a in user["Attributes"]}
        if attrs.get("email"):
            admin_emails.add(attrs["email"])

    users = []
    paginator = client.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=config["user_pool_id"]):
        for user in page["Users"]:
            attrs = {a["Name"]: a["Value"] for a in user["Attributes"]}
            email = attrs.get("email", user["Username"])
            users.append({
                "email": email,
                "name": attrs.get("name") or email.split("@")[0],
                "role": "admin" if email in admin_emails else "subscriber",
                "confirmed": user["UserStatus"] == "CONFIRMED",
                "enabled": user["Enabled"],
                "created_at": user["UserCreateDate"],
            })
    users.sort(key=lambda u: u["created_at"], reverse=True)
    return users


def set_admin(email, is_admin):
    config = _get_config()
    client = _get_client()
    if is_admin:
        client.admin_add_user_to_group(UserPoolId=config["user_pool_id"], Username=email, GroupName="admin")
    else:
        client.admin_remove_user_from_group(UserPoolId=config["user_pool_id"], Username=email, GroupName="admin")


def set_enabled(email, enabled):
    """Disabling blocks sign-in and revokes existing sessions without
    deleting the account or its history — reversible, unlike delete_user()."""
    config = _get_config()
    client = _get_client()
    if enabled:
        client.admin_enable_user(UserPoolId=config["user_pool_id"], Username=email)
    else:
        client.admin_disable_user(UserPoolId=config["user_pool_id"], Username=email)
        try:
            client.admin_user_global_sign_out(UserPoolId=config["user_pool_id"], Username=email)
        except ClientError:
            pass  # no active session to revoke — fine


def delete_user(email):
    config = _get_config()
    try:
        _get_client().admin_delete_user(UserPoolId=config["user_pool_id"], Username=email)
    except ClientError as exc:
        _raise_friendly(exc)


def admin_create_user(email, name, password, make_admin=False):
    """Admin-created account, active immediately with a permanent password
    the admin sets and shares out of band — no Cognito invitation email
    (this User Pool has no custom email templates configured, so the
    default invite reads as generic/spammy) and no email-verification-code
    step (an admin-created account is already vetted by the admin creating
    it)."""
    config = _get_config()
    client = _get_client()
    try:
        client.admin_create_user(
            UserPoolId=config["user_pool_id"],
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ],
            MessageAction="SUPPRESS",
        )
        client.admin_set_user_password(UserPoolId=config["user_pool_id"], Username=email, Password=password, Permanent=True)
        if make_admin:
            set_admin(email, True)
    except ClientError as exc:
        _raise_friendly(exc)


def decode_claims(id_token):
    """Reads every claim out of an ID token WITHOUT verifying its signature.
    That's safe only because every id_token this app ever reads was fetched
    directly from Cognito by this same backend (sign_in()/refresh_tokens()
    above) over a TLS connection this process made itself — it is never
    accepted as input from a client. A token accepted from outside the
    backend would need full JWKS signature verification instead of this."""
    try:
        payload_b64 = id_token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception:
        return {}


def confirm_forgot_password(email, code, new_password):
    config = _get_config()
    try:
        _get_client().confirm_forgot_password(
            ClientId=config["client_id"],
            SecretHash=_secret_hash(email),
            Username=email,
            ConfirmationCode=code,
            Password=new_password,
        )
    except ClientError as exc:
        _raise_friendly(exc)
