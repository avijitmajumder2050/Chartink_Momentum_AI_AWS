"""Verifies Cognito-issued JWTs presented by a client over the network.

This exists because of a real trust-boundary change: connectors/cognito_
connector.py's decode_claims(id_token) does NOT verify the JWT signature —
that was always safe there because that token was only ever freshly fetched
by this same backend, straight from Cognito, over its own TLS connection.
Once the frontend is a separate React SPA sending its own token on every
request (Authorization: Bearer <id_token>), that assumption no longer
holds — a token arriving from outside this process must have its signature,
expiry, audience and issuer checked before any of its claims (especially
cognito:groups, which drives the admin/subscriber role split) are trusted.

Deliberately verifies the ID token, not the OAuth2 access token. Empirically
confirmed against this pool (create a throwaway test user, sign in, inspect
both tokens — see git history/PR notes, not repeated here) that this pool's
access token DOES carry cognito:groups too, so either token would work for
role derivation. ID token was chosen anyway because it also carries a
standard `aud` claim naming the app client, which PyJWT verifies natively;
Cognito's access token uses a `client_id` claim instead of `aud`, which
would need its own manual audience check for no real benefit here. This
also matches this app's existing working behavior — see app.py's
_store_tokens(), which already derives role from
decode_claims(tokens["id_token"]), never the access token.

Mirrors connectors/secrets.py's fetch-and-cache pattern for the JWKS
document (Cognito's public signing keys), keyed by `kid` so a key rotation
on Cognito's side just falls through to a re-fetch instead of ever going
stale in a way that breaks verification.
"""

import time

try:
    import jwt
    from jwt import PyJWKClient
except ImportError:
    jwt = None
    PyJWKClient = None

from connectors import secrets

JWKS_CACHE_TTL_SECONDS = 60 * 60  # Cognito's signing keys rotate rarely, but not never

_config = None
_jwks_client = None
_jwks_client_fetched_at = 0


class TokenVerificationError(Exception):
    pass


def _get_config():
    global _config
    if _config is None:
        _config = {
            "user_pool_id": secrets.get_parameter("/chartink-momentum-ai/cognito/user_pool_id"),
            "region": secrets.get_parameter("/chartink-momentum-ai/cognito/region"),
            # Two valid audiences: the original secret-bearing web client
            # (legacy /api/auth/login fallback, see app.py) and the new
            # public SPA client used by Cognito Hosted UI. Either is
            # accepted so both auth paths work during the Phase-1
            # transition without the backend needing to know which one
            # issued a given token.
            "client_id": secrets.get_parameter("/chartink-momentum-ai/cognito/client_id"),
            "spa_client_id": secrets.get_parameter("/chartink-momentum-ai/cognito/spa_client_id"),
        }
    return _config


def _issuer():
    config = _get_config()
    return f"https://cognito-idp.{config['region']}.amazonaws.com/{config['user_pool_id']}"


def _get_jwks_client():
    # PyJWKClient does its own internal caching of fetched keys by kid, but
    # doesn't expire that cache on its own — rebuilding the client on our
    # own TTL is what actually picks up a Cognito-side key rotation.
    global _jwks_client, _jwks_client_fetched_at
    now = time.time()
    if _jwks_client is None or (now - _jwks_client_fetched_at) >= JWKS_CACHE_TTL_SECONDS:
        jwks_url = f"{_issuer()}/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url)
        _jwks_client_fetched_at = now
    return _jwks_client


def verify_id_token(token):
    """Verifies a Cognito ID token's signature, expiry, audience and
    issuer, and returns its claims dict. Raises TokenVerificationError
    (safe to turn into a 401) on any failure — expired, tampered, wrong
    pool, wrong app client, or not actually an ID token."""
    if jwt is None:
        raise RuntimeError("PyJWT is not installed")
    if not token:
        raise TokenVerificationError("No token provided.")

    config = _get_config()
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=[config["client_id"], config["spa_client_id"]],
            issuer=_issuer(),
        )
    except jwt.PyJWTError as exc:
        raise TokenVerificationError(f"Invalid or expired token: {exc}")

    if claims.get("token_use") != "id":
        raise TokenVerificationError("Expected an ID token.")

    return claims
