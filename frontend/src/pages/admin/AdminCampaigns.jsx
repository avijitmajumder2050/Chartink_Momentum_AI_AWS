import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";

// Ported from templates/admin_campaigns.html. New GET /api/admin/
// campaigns endpoint (app.py) mirrors admin_campaigns_page()'s bootstrap
// data; create/update/delete (already JSON) reused as-is.

function postJson(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) }).then((res) =>
    res.json().then((data) => ({ ok: res.ok, data }))
  );
}

const initialForm = { name: "", code: "", percentOff: 100, planPro: true, planPremium: true, maxRedemptions: "", active: true, visible: true };

export default function AdminCampaigns() {
  const [campaigns, setCampaigns] = useState(null);
  const [error, setError] = useState(false);
  const [message, setMessage] = useState(null);
  const [form, setForm] = useState(initialForm);

  const loadCampaigns = () => {
    setError(false);
    return apiFetch("/api/admin/campaigns")
      .then((res) => res.json())
      .then((data) => setCampaigns(data.campaigns))
      .catch(() => setError(true));
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  function showMessage(text, isError) {
    setMessage({ text, isError });
  }

  function submitForm(e) {
    e.preventDefault();
    const applicablePlans = [];
    if (form.planPro) applicablePlans.push("pro");
    if (form.planPremium) applicablePlans.push("premium");

    postJson("/api/admin/campaigns", {
      name: form.name,
      code: form.code,
      percentOff: Number(form.percentOff),
      applicablePlans,
      maxRedemptions: form.maxRedemptions ? Number(form.maxRedemptions) : null,
      active: form.active,
      visible: form.visible,
    }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't create campaign.", true);
        return;
      }
      showMessage("Campaign created.", false);
      setForm(initialForm);
      loadCampaigns();
    });
  }

  function toggleField(code, field, checked) {
    postJson(`/api/admin/campaigns/${encodeURIComponent(code)}/update`, { [field]: checked }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't update.", true);
        loadCampaigns(); // revert the optimistic toggle by re-fetching
        return;
      }
      showMessage(`${code} updated.`, false);
    });
  }

  function deleteCampaign(code) {
    if (!window.confirm(`Delete campaign ${code}? This can't be undone.`)) return;
    postJson(`/api/admin/campaigns/${encodeURIComponent(code)}/delete`, {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete.", true);
        return;
      }
      setCampaigns((prev) => prev.filter((c) => c.code !== code));
    });
  }

  if (error) {
    return (
      <div style={{ padding: "60px 36px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>Couldn't load campaigns right now.</p>
        <button
          type="button"
          onClick={loadCampaigns}
          style={{ background: "#4640DE", color: "white", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "10px 20px", borderRadius: 9 }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (campaigns === null) return null;

  return (
    <div style={{ padding: "30px clamp(16px, 4vw, 36px) 90px" }}>
      <div style={{ maxWidth: 1040 }}>
        <div style={{ marginBottom: 24 }}>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Admin</span>
          <h1 style={{ fontSize: 26, fontWeight: 800, marginTop: 6 }}>Voucher campaigns</h1>
          <p style={{ fontSize: 13.5, color: "#5B6270", margin: "6px 0 0" }}>
            Create discount codes for Pro/Premium. "Active" controls whether a code actually works; "Visible" controls whether it's advertised on the subscription page.
          </p>
        </div>

        {message && (
          <div style={{ fontSize: 13, fontWeight: 600, padding: "11px 14px", borderRadius: 10, marginBottom: 20, background: message.isError ? "#FDEDEC" : "#EAF7F1", color: message.isError ? "#C0392B" : "#17A673" }}>
            {message.text}
          </div>
        )}

        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24, marginBottom: 28 }}>
          <span style={{ fontSize: 15, fontWeight: 700, display: "block", marginBottom: 16 }}>New campaign</span>
          <form onSubmit={submitForm} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, alignItems: "end" }}>
            <label style={{ gridColumn: "span 2" }}>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Campaign name</span>
              <input type="text" required placeholder="e.g. Diwali 2026" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} style={inputStyle} />
            </label>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Voucher code</span>
              <input type="text" required placeholder="DIWALI30" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} style={{ ...inputStyle, textTransform: "uppercase" }} />
            </label>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Discount %</span>
              <input type="number" required min="1" max="100" value={form.percentOff} onChange={(e) => setForm((f) => ({ ...f, percentOff: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ gridColumn: "span 2" }}>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Applies to</span>
              <span style={{ display: "flex", gap: 16, padding: "11px 0" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
                  <input type="checkbox" checked={form.planPro} onChange={(e) => setForm((f) => ({ ...f, planPro: e.target.checked }))} /> Pro
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
                  <input type="checkbox" checked={form.planPremium} onChange={(e) => setForm((f) => ({ ...f, planPremium: e.target.checked }))} /> Premium
                </label>
              </span>
            </label>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Max redemptions</span>
              <input type="number" min="1" placeholder="Unlimited" value={form.maxRedemptions} onChange={(e) => setForm((f) => ({ ...f, maxRedemptions: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, padding: "11px 0" }}>
              <input type="checkbox" checked={form.active} onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))} /> Active
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, padding: "11px 0" }}>
              <input type="checkbox" checked={form.visible} onChange={(e) => setForm((f) => ({ ...f, visible: e.target.checked }))} /> Visible to subscribers
            </label>
            <button type="submit" style={{ gridColumn: "span 2", background: "#4640DE", color: "white", border: "none", fontSize: 13.5, fontWeight: 700, padding: "12px 0", borderRadius: 9, cursor: "pointer" }}>
              Create campaign
            </button>
          </form>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
          <div className="table-wrap">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #E3E6EC" }}>
                {["Campaign", "Code", "Discount", "Plans", "Redeemed", "Active", "Visible", ""].map((h) => (
                  <th key={h} style={{ padding: "12px 16px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!campaigns.length ? (
                <tr><td colSpan={8} style={{ padding: "24px 16px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>No campaigns yet — create one above.</td></tr>
              ) : (
                campaigns.map((c) => (
                  <tr key={c.code} style={{ borderBottom: "1px solid #F0F1F4" }}>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontWeight: 600 }}>{c.name}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontFamily: "'IBM Plex Mono', monospace" }}>{c.code}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13 }}>{c.percent_off}%</td>
                    <td style={{ padding: "12px 16px", fontSize: 12.5, color: "#5B6270" }}>{c.applicable_plans.join(", ")}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13 }}>{c.redemption_count}{c.max_redemptions ? `/${c.max_redemptions}` : ""}</td>
                    <td style={{ padding: "12px 16px" }}>
                      <input type="checkbox" defaultChecked={c.active} onChange={(e) => toggleField(c.code, "active", e.target.checked)} />
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <input type="checkbox" defaultChecked={c.visible} onChange={(e) => toggleField(c.code, "visible", e.target.checked)} />
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <button type="button" onClick={() => deleteCampaign(c.code)} style={{ background: "none", border: "none", color: "#E0473F", fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  );
}

const inputStyle = { width: "100%", border: "1.5px solid #E3E6EC", borderRadius: 9, padding: "10px 12px", fontSize: 13, fontFamily: "inherit" };
