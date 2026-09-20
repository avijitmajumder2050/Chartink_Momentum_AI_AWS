import { Link } from "react-router-dom";
import { useAuth } from "./AuthContext";
import RequireAuth from "./RequireAuth";

// Gates a route to paying subscribers (pro/premium) — admins always pass,
// same "admin can see everything" convention RequireAdmin already uses.
// Mirrors RequireAdmin.jsx's shape exactly, checking plan instead of
// role. The matching API endpoints are gated server-side too (app.py's
// subscription_required) — this only controls what the SPA shows; it
// isn't the actual security boundary.
function UpgradeRequired() {
  const { user } = useAuth();
  return (
    <div style={{ width: "100%", padding: "64px clamp(16px, 5vw, 48px)" }}>
      <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "clamp(16px, 5vw, 48px) 36px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>This needs a Pro or Premium plan</h2>
        <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: "0 0 22px" }}>
          Signed in as <strong>{user.email}</strong> ({user.plan === "free" ? "Free plan" : user.plan}). Upgrade to unlock live charts, the scanner, IPO tracking, and stock research.
        </p>
        <Link to="/pricing" style={{ display: "inline-block", background: "#4640DE", color: "white", fontSize: 13.5, fontWeight: 700, padding: "11px 22px", borderRadius: 10 }}>
          View plans
        </Link>
      </div>
    </div>
  );
}

function SubscriptionCheck({ children }) {
  const { user } = useAuth();
  if (user.role !== "admin" && user.plan !== "pro" && user.plan !== "premium") return <UpgradeRequired />;
  return children;
}

export default function RequireSubscription({ children }) {
  return (
    <RequireAuth>
      <SubscriptionCheck>{children}</SubscriptionCheck>
    </RequireAuth>
  );
}
