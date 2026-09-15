import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { cognitoConfig } from "../config";
import { getTokens, clearTokens } from "./tokenStore";
import { redirectToLogin, redirectToLogout } from "./pkce";
import { apiFetch } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // "loading" until the initial /api/auth/me check resolves, so routes
  // that require auth don't flash a logged-out state on every page load
  // while that request is in flight.
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Returns whether it actually landed on a signed-in user — most callers
  // (the mount-time check, a 401 elsewhere) don't care and can ignore it,
  // but Callback.jsx uses it to retry a transient post-login failure
  // instead of silently leaving the user looking logged-out despite
  // already having valid tokens stored.
  const refreshCurrentUser = useCallback(async () => {
    if (!getTokens()) {
      setUser(null);
      setLoading(false);
      return false;
    }
    try {
      const response = await apiFetch("/api/auth/me");
      if (response.ok) {
        setUser(await response.json());
        return true;
      }
      clearTokens();
      setUser(null);
      return false;
    } catch {
      setUser(null);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCurrentUser();
  }, [refreshCurrentUser]);

  const login = useCallback(() => redirectToLogin(cognitoConfig), []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    redirectToLogout(cognitoConfig);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshCurrentUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
