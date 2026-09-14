import { Link } from "react-router-dom";
import { useAuth } from "./AuthContext";
import RequireAuth from "./RequireAuth";

// Ported from templates/access_denied.html. Like role_required("admin")
// server-side: a signed-in but wrong-role user sees this instead of the
// page, rather than being bounced back to login they already passed.
function AccessDenied() {
  const { user } = useAuth();
  return (
    <div style={{ width: "100%", padding: "64px 48px" }}>
      <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>You don't have access to this page</h2>
        <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: "0 0 22px" }}>
          Signed in as <strong>{user.email}</strong> ({user.role}). This page needs a different role.
        </p>
        <Link to="/dashboard" style={{ display: "inline-block", background: "#4640DE", color: "white", fontSize: 13.5, fontWeight: 700, padding: "11px 22px", borderRadius: 10 }}>
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}

function AdminCheck({ children }) {
  const { user } = useAuth();
  if (user.role !== "admin") return <AccessDenied />;
  return children;
}

export default function RequireAdmin({ children }) {
  return (
    <RequireAuth>
      <AdminCheck>{children}</AdminCheck>
    </RequireAuth>
  );
}
