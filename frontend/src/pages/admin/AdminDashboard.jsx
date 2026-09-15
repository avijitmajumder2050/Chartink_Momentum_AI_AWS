import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../../api/client";

// Ported from templates/admin_dashboard.html. New GET /api/admin/dashboard
// (app.py) mirrors admin_dashboard()'s exact logic.
const PLAN_MIX = [
  ["Free", "free", "#D8DAE3"],
  ["Pro", "pro", "#4640DE"],
  ["Premium", "premium", "#B98A2E"],
];

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export default function AdminDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setError(false);
    apiFetch("/api/admin/dashboard")
      .then((res) => res.json())
      .then(setData)
      .catch(() => setError(true));
  }, [retryCount]);

  if (error) {
    return (
      <div style={{ padding: "60px 36px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>Couldn't load the admin dashboard right now.</p>
        <button
          type="button"
          onClick={() => setRetryCount((c) => c + 1)}
          style={{ background: "#4640DE", color: "white", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "10px 20px", borderRadius: 9 }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;
  const { stats, recentUsers, totalUserCount, adminCount } = data;
  const mixTotal = stats.plan_counts.free + stats.plan_counts.pro + stats.plan_counts.premium;

  return (
    <div style={{ padding: "30px clamp(16px, 4vw, 36px) 60px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 26, flexWrap: "wrap", gap: 12 }}>
        <div>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>Overview</span>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginTop: 2 }}>Admin dashboard</h1>
        </div>
        {/* CSV export needs a signed URL (see /admin/users page) — link
            there rather than exporting straight from the overview. */}
        <Link to="/admin/users" style={{ background: "#4640DE", color: "white", borderRadius: 10, padding: "9px 16px", fontSize: 13, fontWeight: 700, textDecoration: "none" }}>
          Export users CSV
        </Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 22 }}>
        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>Total users</span>
          <div className="num" style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>{totalUserCount.toLocaleString("en-IN")}</div>
        </div>
        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>Paid subscribers</span>
          <div className="num" style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>{(stats.plan_counts.pro + stats.plan_counts.premium).toLocaleString("en-IN")}</div>
        </div>
        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>Monthly recurring revenue</span>
          <div className="num" style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>₹{Math.floor(stats.mrr_paise / 100).toLocaleString("en-IN")}</div>
        </div>
        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: 18 }}>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>Admins</span>
          <div className="num" style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>{adminCount}</div>
        </div>
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 22 }}>
        <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Plan mix — real, current snapshot (no historical trend is stored)</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {PLAN_MIX.map(([label, key, color]) => (
            <div key={key}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 5 }}>
                <span style={{ color: "#5B6270" }}>{label}</span>
                <span className="num" style={{ fontWeight: 700 }}>{stats.plan_counts[key]}</span>
              </div>
              <div style={{ width: "100%", height: 7, background: "#F0F1F4", borderRadius: 100 }}>
                <div style={{ width: `${mixTotal ? Math.round((stats.plan_counts[key] / mixTotal) * 1000) / 10 : 0}%`, height: 7, background: color, borderRadius: 100 }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: "6px 0 8px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 22px 12px" }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>Recent users</span>
          <Link to="/admin/users" style={{ fontSize: 12.5, fontWeight: 700, color: "#4640DE" }}>View all →</Link>
        </div>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              {["User", "Role", "Plan", "Status", "Joined"].map((h) => (
                <th key={h} style={{ textAlign: "left", fontSize: 11.5, fontWeight: 600, color: "#8A90A0", textTransform: "uppercase", letterSpacing: "0.04em", padding: "0 14px 10px" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {recentUsers.map((u) => (
              <tr key={u.email}>
                <td style={{ padding: "12px 14px", fontSize: 13, borderTop: "1px solid #F0F1F4" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#4640DE", color: "white", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {u.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, display: "block" }}>{u.name}</span>
                      <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{u.email}</span>
                    </div>
                  </div>
                </td>
                <td style={{ padding: "12px 14px", fontSize: 13, borderTop: "1px solid #F0F1F4", textTransform: "capitalize" }}>{u.role}</td>
                <td style={{ padding: "12px 14px", fontSize: 13, borderTop: "1px solid #F0F1F4" }}>{u.plan}</td>
                <td style={{ padding: "12px 14px", fontSize: 13, borderTop: "1px solid #F0F1F4" }}>{u.sub_status}</td>
                <td style={{ padding: "12px 14px", fontSize: 13, borderTop: "1px solid #F0F1F4" }}>{fmtDate(u.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
