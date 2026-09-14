// PKCE (Proof Key for Code Exchange) helpers for the Cognito Hosted UI
// Authorization Code flow — required because this app client is public
// (no client_secret, see connectors/auth_verify.py's docstring for why),
// so a plain authorization-code exchange without PKCE would let anyone
// who intercepts the redirect's `code` trade it for tokens themselves.

const VERIFIER_STORAGE_KEY = "quantile_pkce_verifier";

function randomString(length) {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  // Unreserved URL-safe characters only, per RFC 7636's code_verifier charset.
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

function base64UrlEncode(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function codeChallengeFor(verifier) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncode(digest);
}

// Kicks off login by redirecting to Cognito's Hosted UI — call this
// directly from a "Log in" button's onClick, there's no return value
// because the whole point is navigating away.
export async function redirectToLogin(config) {
  const verifier = randomString(64);
  sessionStorage.setItem(VERIFIER_STORAGE_KEY, verifier);
  const challenge = await codeChallengeFor(verifier);

  const params = new URLSearchParams({
    client_id: config.clientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: config.redirectUri,
    code_challenge_method: "S256",
    code_challenge: challenge,
  });
  window.location.href = `https://${config.domain}/oauth2/authorize?${params.toString()}`;
}

export function redirectToLogout(config) {
  sessionStorage.removeItem(VERIFIER_STORAGE_KEY);
  const params = new URLSearchParams({
    client_id: config.clientId,
    logout_uri: config.logoutUri,
  });
  window.location.href = `https://${config.domain}/logout?${params.toString()}`;
}

// Exchanges the `code` Cognito's redirect handed back for real tokens —
// called once by the /auth/callback route. Talks to Cognito's token
// endpoint directly from the browser (no Flask proxy needed: this app
// client has no secret, so nothing here needs to stay server-side), using
// the code_verifier stashed before the redirect so Cognito can confirm
// this exchange is coming from the same browser that started the flow.
export async function exchangeCodeForTokens(config, code) {
  const verifier = sessionStorage.getItem(VERIFIER_STORAGE_KEY);
  if (!verifier) {
    throw new Error("No PKCE code_verifier found — the login flow may have been started in a different tab or expired.");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: verifier,
  });

  const response = await fetch(`https://${config.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  sessionStorage.removeItem(VERIFIER_STORAGE_KEY);

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Token exchange failed (${response.status}): ${detail}`);
  }

  // { id_token, access_token, refresh_token, expires_in, token_type }
  return response.json();
}

// Silent refresh — called by the API client on a 401, and could also be
// called proactively on a timer later. No code_verifier needed here,
// refresh_token grants don't use PKCE.
export async function refreshTokens(config, refreshToken) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: config.clientId,
    refresh_token: refreshToken,
  });

  const response = await fetch(`https://${config.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`Token refresh failed (${response.status})`);
  }

  // Cognito's refresh grant doesn't return a new refresh_token — the
  // original keeps working until it hits its own (much longer) expiry.
  return response.json();
}
