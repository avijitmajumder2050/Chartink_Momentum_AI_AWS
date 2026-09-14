import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";

// Ported from templates/admin_subscriptions.html. New GET /api/admin/
// subscriptions endpoint (app.py) mirrors admin_subscriptions_page()'s
// list_all_subscriptions() call — read-only, no actions on this page.
const STATUS_STYLE = {
  active: { color: "#17A673", background: "#E6F7F1" },
  canceled: { color: "#B98A2E", background: "#FBF2E1" },
};
const DEFAULT_STATUS_STYLE = { color: "#E0473F", background: "#FCEBEA" };

export default function AdminSubscriptions() {
  const [subscriptions, setSubscriptions] = useState(null);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setError(false);
    apiFetch("/api/admin/subscriptions")
      .then((res) => res.json())
      .then((data) => setSubscriptions(data.subscriptions))
      .catch(() => setError(true));
  }, [retryCount]);

  if (error) {
    return (
      <div style={{ padding: "60px 36px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>Couldn't load subscriptions right now.</p>
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

  if (subscriptions === null) return null;

  return (
    <div style={{ padding: "30px 36px 60px" }}>
      <div style={{ marginBottom: 22 }}>
        <span style={{ fontSize: 12, color: "#8A90A0" }}>{subscriptions.length} accounts with subscription history</span>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginTop: 2 }}>Subscriptions</h1>
        <p style={{ fontSize: 13, color: "#5B6270", marginTop: 6 }}>Accounts that have never redeemed a voucher or paid don't appear here — they're implicitly on the Free plan.</p>
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
              {["Email", "Plan", "Status", "Period end", "Voucher", "Razorpay sub", "Updated"].map((h) => (
                <th key={h} style={{ padding: "12px 16px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!subscriptions.length ? (
              <tr><td colSpan={7} style={{ padding: "30px 16px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>No subscription activity yet — everyone's on the implicit Free plan.</td></tr>
            ) : (
              subscriptions.map((s) => {
                const style = STATUS_STYLE[s.status] || DEFAULT_STATUS_STYLE;
                return (
                  <tr key={s.email} style={{ borderBottom: "1px solid #F0F1F4" }}>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontWeight: 600 }}>{s.email}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13, textTransform: "capitalize" }}>{s.plan}</td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: 100, ...style }}>{s.status}</span>
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: 13 }}>{s.current_period_end ? s.current_period_end.slice(0, 10) : "—"}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontFamily: "'IBM Plex Mono', monospace" }}>{s.voucher_code || "—"}</td>
                    <td style={{ padding: "12px 16px", fontSize: 12, color: "#8A90A0" }}>{s.razorpay_subscription_id || "—"}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13 }}>{s.updated_at ? s.updated_at.slice(0, 10) : "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
