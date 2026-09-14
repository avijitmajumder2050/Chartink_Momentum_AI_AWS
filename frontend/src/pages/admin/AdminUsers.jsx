import { useMemo, useState, useEffect } from "react";
import { apiFetch } from "../../api/client";
import { API_BASE_URL } from "../../config";
import { useAuth } from "../../auth/AuthContext";

// Ported from templates/admin_users.html. New GET /api/admin/users
// mirrors admin_users_page()'s join logic; role/enabled/delete/create
// (already JSON) reused as-is. CSV export uses the new signed-URL flow
// (POST /api/admin/users/export-link -> GET /admin/users/export.csv) —
// see app.py's _sign_export_token for why a plain bearer header doesn't
// work for a browser-navigated file download.

function postJson(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) }).then((res) =>
    res.json().then((data) => ({ ok: res.ok, data }))
  );
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export default function AdminUsers() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", email: "", password: "", makeAdmin: false });
  const [addResult, setAddResult] = useState(null);
  const [busyEmail, setBusyEmail] = useState(null);

  const loadUsers = () => apiFetch("/api/admin/users").then((res) => res.json()).then((data) => setUsers(data.users));

  useEffect(() => {
    loadUsers();
  }, []);

  function showMessage(text, isError) {
    setMessage({ text, isError });
  }

  const filtered = useMemo(() => {
    if (!users) return [];
    const q = search.toLowerCase().trim();
    if (!q) return users;
    return users.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(q));
  }, [users, search]);

  function exportCsv() {
    postJson("/api/admin/users/export-link", {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't prepare the export.", true);
        return;
      }
      window.location.href = API_BASE_URL + result.data.downloadUrl;
    });
  }

  function submitAddUser(e) {
    e.preventDefault();
    postJson("/api/admin/users", {
      name: addForm.name,
      email: addForm.email,
      password: addForm.password || undefined,
      makeAdmin: addForm.makeAdmin,
    }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't create user.", true);
        return;
      }
      setAddResult({ email: result.data.email, password: result.data.password });
      setAddForm({ name: "", email: "", password: "", makeAdmin: false });
      loadUsers();
    });
  }

  function toggleRole(u) {
    const makeAdmin = u.role !== "admin";
    if (!window.confirm(`${makeAdmin ? "Make " : "Remove admin access from "}${u.email}?`)) return;
    setBusyEmail(u.email);
    postJson(`/api/admin/users/${encodeURIComponent(u.email)}/role`, { admin: makeAdmin }).then((result) => {
      setBusyEmail(null);
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't update role.", true);
        return;
      }
      showMessage(`${u.email} is now ${makeAdmin ? "an admin" : "a subscriber"}.`, false);
      loadUsers();
    });
  }

  function toggleEnabled(u) {
    const enable = !u.enabled;
    const msg = enable ? `Re-enable ${u.email}?` : `Disable ${u.email}? They'll be signed out and unable to log in until re-enabled.`;
    if (!window.confirm(msg)) return;
    setBusyEmail(u.email);
    postJson(`/api/admin/users/${encodeURIComponent(u.email)}/enabled`, { enabled: enable }).then((result) => {
      setBusyEmail(null);
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't update status.", true);
        return;
      }
      showMessage(`${u.email} is now ${enable ? "active" : "disabled"}.`, false);
      loadUsers();
    });
  }

  function deleteUser(u) {
    if (!window.confirm(`Permanently delete ${u.email}? This cannot be undone.`)) return;
    setBusyEmail(u.email);
    postJson(`/api/admin/users/${encodeURIComponent(u.email)}/delete`, {}).then((result) => {
      setBusyEmail(null);
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete user.", true);
        return;
      }
      showMessage(`${u.email} deleted.`, false);
      setUsers((prev) => prev.filter((x) => x.email !== u.email));
    });
  }

  if (users === null) return null;

  return (
    <div style={{ padding: "30px 36px 60px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22, flexWrap: "wrap", gap: 12 }}>
        <div>
          <span style={{ fontSize: 12, color: "#8A90A0" }}>{users.length} total</span>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginTop: 2 }}>Users</h1>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ border: "1.5px solid #E3E6EC", borderRadius: 9, padding: "9px 14px", fontSize: 13, width: 220 }}
          />
          <button type="button" onClick={exportCsv} style={{ border: "1.5px solid #E3E6EC", background: "#FFFFFF", color: "#14171F", borderRadius: 9, padding: "9px 16px", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
            Export CSV
          </button>
          <button type="button" onClick={() => setShowAddForm((v) => !v)} style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 9, padding: "9px 16px", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
            + Add user
          </button>
        </div>
      </div>

      {message && (
        <div style={{ fontSize: 13, fontWeight: 600, padding: "11px 14px", borderRadius: 10, marginBottom: 16, background: message.isError ? "#FDEDEC" : "#EAF7F1", color: message.isError ? "#C0392B" : "#17A673" }}>
          {message.text}
        </div>
      )}

      {showAddForm && (
        <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 20 }}>
          <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Add a user</span>
          <form onSubmit={submitAddUser} style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 14, alignItems: "end" }}>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Full name</span>
              <input type="text" required value={addForm.name} onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))} style={auInput} />
            </label>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Email</span>
              <input type="email" required value={addForm.email} onChange={(e) => setAddForm((f) => ({ ...f, email: e.target.value }))} style={auInput} />
            </label>
            <label>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Password (optional)</span>
              <input type="text" placeholder="Auto-generated if blank" value={addForm.password} onChange={(e) => setAddForm((f) => ({ ...f, password: e.target.value }))} style={auInput} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, padding: "10px 0" }}>
              <input type="checkbox" checked={addForm.makeAdmin} onChange={(e) => setAddForm((f) => ({ ...f, makeAdmin: e.target.checked }))} /> Make admin
            </label>
            <button type="submit" style={{ gridColumn: "span 2", background: "#4640DE", color: "white", border: "none", fontSize: 13.5, fontWeight: 700, padding: "11px 0", borderRadius: 9, cursor: "pointer" }}>
              Create user
            </button>
          </form>
          {addResult && (
            <div style={{ marginTop: 14, padding: "12px 14px", background: "#FBF2E1", borderRadius: 10, fontSize: 13 }}>
              Created <strong>{addResult.email}</strong> — share this password with them:{" "}
              <code style={{ background: "#fff", padding: "2px 6px", borderRadius: 5 }}>{addResult.password}</code>
            </div>
          )}
        </div>
      )}

      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
              {["User", "Plan", "Status", "Joined", "Role", ""].map((h) => (
                <th key={h} style={{ padding: "12px 16px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr key={u.email} style={{ borderBottom: "1px solid #F0F1F4" }}>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#4640DE", color: "white", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {u.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, display: "block", fontSize: 13 }}>{u.name}</span>
                      <span style={{ fontSize: 11.5, color: "#8A90A0" }}>{u.email}</span>
                    </div>
                  </div>
                </td>
                <td style={{ padding: "12px 16px", fontSize: 13 }}>{u.plan}</td>
                <td style={{ padding: "12px 16px" }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: 100, color: u.enabled ? "#17A673" : "#E0473F", background: u.enabled ? "#E6F7F1" : "#FCEBEA" }}>
                    {u.enabled ? "Active" : "Disabled"}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: 13 }}>{fmtDate(u.created_at)}</td>
                <td style={{ padding: "12px 16px" }}>
                  <button
                    type="button"
                    disabled={busyEmail === u.email}
                    onClick={() => toggleRole(u)}
                    style={{ fontSize: 11.5, fontWeight: 700, padding: "5px 11px", borderRadius: 100, border: "none", cursor: "pointer", background: u.role === "admin" ? "#EEEDFD" : "#F0F1F4", color: u.role === "admin" ? "#4640DE" : "#5B6270" }}
                  >
                    {u.role === "admin" ? "Admin — remove" : "Make admin"}
                  </button>
                </td>
                <td style={{ padding: "12px 16px", whiteSpace: "nowrap" }}>
                  <button
                    type="button"
                    disabled={busyEmail === u.email}
                    onClick={() => toggleEnabled(u)}
                    style={{ fontSize: 11.5, fontWeight: 700, padding: "5px 10px", borderRadius: 7, border: "none", cursor: "pointer", background: "#F0F1F4", color: "#5B6270", marginRight: 6 }}
                  >
                    {u.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    disabled={busyEmail === u.email || u.email === currentUser?.email}
                    onClick={() => deleteUser(u)}
                    style={{ fontSize: 11.5, fontWeight: 700, padding: "5px 10px", borderRadius: 7, border: "none", cursor: "pointer", background: "#FCEBEA", color: "#E0473F" }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const auInput = { width: "100%", border: "1.5px solid #E3E6EC", borderRadius: 9, padding: "9px 11px", fontSize: 13, fontFamily: "inherit" };
