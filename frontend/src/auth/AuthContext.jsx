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

  const refreshCurrentUser = useCallback(async () => {
    if (!getTokens()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const response = await apiFetch("/api/auth/me");
      if (response.ok) {
        setUser(await response.json());
      } else {
        clearTokens();
        setUser(null);
      }
    } catch {
      setUser(null);
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
