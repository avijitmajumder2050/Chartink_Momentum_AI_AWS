import { cognitoConfig, API_BASE_URL } from "../config";
import { getTokens, setTokens, clearTokens, isExpired } from "../auth/tokenStore";
import { refreshTokens, redirectToLogin } from "../auth/pkce";

// Prevents a burst of concurrent requests (e.g. a page firing several
// fetches on mount) each independently noticing an expired token and
// racing to refresh it — every caller awaits the same in-flight refresh.
let refreshInFlight = null;

async function ensureFreshTokens() {
  const tokens = getTokens();
  if (!tokens) return null;
  if (!isExpired(tokens)) return tokens;
  if (!tokens.refreshToken) {
    clearTokens();
    return null;
  }

  if (!refreshInFlight) {
    refreshInFlight = refreshTokens(cognitoConfig, tokens.refreshToken)
      .then((response) => setTokens(response))
      .catch((err) => {
        clearTokens();
        throw err;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// The single place every page/component calls the Flask JSON API through
// — injects the bearer ID token (see connectors/auth_verify.py for why
// it's the ID token, not the OAuth2 access token), refreshes it first if
// it's past expiry, and retries exactly once on a 401 in case the token
// was rejected for a reason the client-side expiry check didn't catch
// (e.g. an admin revoking the session). Falls back to a fresh Hosted UI
// login if refresh itself fails.
export async function apiFetch(path, options = {}) {
  let tokens;
  try {
    tokens = await ensureFreshTokens();
  } catch {
    await redirectToLogin(cognitoConfig);
    return new Promise(() => {}); // navigation is in flight; never resolve
  }

  const doFetch = (bearerToken) =>
    fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {}),
        ...options.headers,
      },
    });

  let response = await doFetch(tokens?.idToken);

  if (response.status === 401 && tokens?.refreshToken) {
    try {
      const refreshed = await refreshTokens(cognitoConfig, tokens.refreshToken);
      tokens = setTokens(refreshed);
      response = await doFetch(tokens.idToken);
    } catch {
      clearTokens();
      await redirectToLogin(cognitoConfig);
      return new Promise(() => {});
    }
  }

  return response;
}
