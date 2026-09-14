import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Stub — templates/home.html is a full marketing landing page backed by
// mock_data.py, ported properly in Phase 4 of the rewrite plan alongside
// the mock_data.py static-vs-API decision. This exists only so the app
// has a working "/" route and the auth flow has somewhere to land.
export default function Home() {
  const { user, loading } = useAuth();

  return (
    <div style={{ padding: "76px 48px", textAlign: "center" }}>
      <h1 style={{ fontSize: 32, fontWeight: 800, marginBottom: 12 }}>Quantile</h1>
      {loading ? (
        <p>Loading…</p>
      ) : user ? (
        <p>
          Signed in as <strong>{user.email}</strong> ({user.role}, {user.plan} plan).
        </p>
      ) : (
        <p>Not signed in.</p>
      )}
      <p style={{ marginTop: 24 }}>
        <Link to="/capabilities">See capabilities →</Link>
      </p>
    </div>
  );
}
