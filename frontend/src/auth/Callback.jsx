import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { cognitoConfig } from "../config";
import { exchangeCodeForTokens } from "./pkce";
import { setTokens } from "./tokenStore";
import { useAuth } from "./AuthContext";

// Route target for Cognito Hosted UI's redirect_uri (?code=...). Exchanges
// the code for tokens, stores them, refreshes the auth context's current
// user, then leaves this URL for the app's home page — a real page, not
// a query string with a one-time code in it.
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

    exchangeCodeForTokens(cognitoConfig, code)
      .then((tokens) => {
        setTokens(tokens);
        return refreshCurrentUser();
      })
      .then(() => navigate("/", { replace: true }))
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
