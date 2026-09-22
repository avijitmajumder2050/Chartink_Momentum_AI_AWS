import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { cognitoConfig } from "../config";
import { exchangeCodeForTokens, consumePostLoginRedirect } from "./pkce";
import { setTokens } from "./tokenStore";
import { useAuth } from "./AuthContext";

// Route target for Cognito Hosted UI's redirect_uri (?code=...). Exchanges
// the code for tokens, stores them, refreshes the auth context's current
// user, then leaves this URL for wherever the user actually wanted to be
// (consumePostLoginRedirect() — a real page, not a query string with a
// one-time code in it) instead of always landing on home.
export default function Callback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshCurrentUser } = useAuth();
  const [error, setError] = useState(null);
  const ranOnce = useRef(false);

  useEffect(() => {
    // StrictMode double-invokes effects in dev — without this guard the
    // second run would try to reuse an already-consumed code_verifier.
    if (ranOnce.current) return;
    ranOnce.current = true;

    const code = searchParams.get("code");
    const errorParam = searchParams.get("error");
    if (errorParam) {
      setError(searchParams.get("error_description") || errorParam);
      return;
    }
    if (!code) {
      setError("No authorization code in the redirect.");
      return;
    }

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    exchangeCodeForTokens(cognitoConfig, code)
      .then(async (tokens) => {
        // /api/auth/me occasionally fails on the very first call right
        // after a fresh login (e.g. a cold JWKS fetch server-side) —
        // refreshCurrentUser() treats that like an invalid token and
        // clears it, which would otherwise strand the user on a page
        // that looks logged-out despite Cognito having just handed back
        // good tokens. Re-store the same (real, freshly-issued) tokens
        // before each retry so a transient failure doesn't get treated
        // as a reason to give up on them.
        setTokens(tokens);
        let signedIn = await refreshCurrentUser();
        for (let attempt = 0; !signedIn && attempt < 2; attempt++) {
          await sleep(500 * (attempt + 1));
          setTokens(tokens);
          signedIn = await refreshCurrentUser();
        }
        if (!signedIn) {
          throw new Error("Signed in, but couldn't load your account. Please try again.");
        }
      })
      .then(() => navigate(consumePostLoginRedirect(), { replace: true }))
      .catch((err) => setError(err.message));
  }, [searchParams, navigate, refreshCurrentUser]);

  if (error) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <p style={{ color: "var(--down)", fontWeight: 600 }}>Sign-in failed: {error}</p>
        <a href="/">Back to home</a>
      </div>
    );
  }

  return <div style={{ padding: 48, textAlign: "center" }}>Signing you in…</div>;
}
