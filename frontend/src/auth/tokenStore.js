// Token persistence — sessionStorage (not localStorage) so tokens don't
// survive past the browser tab closing, and don't leak across tabs the
// way localStorage would. A stolen sessionStorage token via XSS is still
// a real risk (same as any bearer-token SPA without a BFF layer) — worth
// revisiting later, not a Phase-1 concern.

const STORAGE_KEY = "quantile_tokens";

export function getTokens() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setTokens({ id_token, access_token, refresh_token, expires_in }) {
  const existing = getTokens();
  const tokens = {
    idToken: id_token,
    accessToken: access_token,
    // Cognito's refresh grant doesn't return a new refresh_token — keep
    // the one we already had if this call didn't hand back a fresh one.
    refreshToken: refresh_token || existing?.refreshToken,
    // 60s safety margin, same convention as the old Flask session's
    // token_expires_at, so a request doesn't start with a token that
    // expires mid-flight.
    expiresAt: Date.now() + expires_in * 1000 - 60_000,
  };
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  return tokens;
}

export function clearTokens() {
  sessionStorage.removeItem(STORAGE_KEY);
}

export function isExpired(tokens) {
  return !tokens || Date.now() >= tokens.expiresAt;
}
