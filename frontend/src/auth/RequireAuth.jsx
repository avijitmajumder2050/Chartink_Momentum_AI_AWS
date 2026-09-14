import { useEffect } from "react";
import { useAuth } from "./AuthContext";

// Guards a route the way login_required did server-side — redirects to
// Cognito Hosted UI if there's no signed-in user once the initial
// /api/auth/me check has resolved. Renders nothing useful until then, so
// a protected page never flashes its real content before the redirect.
export default function RequireAuth({ children }) {
  const { user, loading, login } = useAuth();

  useEffect(() => {
    if (!loading && !user) login();
  }, [loading, user, login]);

  if (loading || !user) {
    return <div style={{ padding: 48, textAlign: "center" }}>Loading…</div>;
  }
  return children;
}
