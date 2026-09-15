import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import { usePushNotifications } from "../push/PushNotificationsContext";

const LS_LAST_SEEN = "quantile_last_seen_notif";

function timeAgo(iso) {
  const diffMin = Math.max(0, Math.round((Date.now() - new Date(iso + "Z").getTime()) / 60000));
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 1440) return `${Math.round(diffMin / 60)}h ago`;
  return `${Math.round(diffMin / 1440)}d ago`;
}

// Same Markdown-style "[Label](https://...)" CTA convention used by the
// campaign builder's preview — renders a clean clickable label, never
// the raw URL.
function linkify(text) {
  const parts = [];
  const re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = re.exec(text))) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push(
      <a key={key++} href={match[2]} target="_blank" rel="noopener noreferrer" className="notif-card-link">
        {match[1]}
      </a>
    );
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

const BELL_ICON = (
  <svg width="19" height="19" viewBox="0 0 19 19" fill="none" stroke="#5B6270" strokeWidth="1.6">
    <path d="M4 8a5.5 5.5 0 0 1 11 0c0 3 1 4 1.5 5H2.5C3 12 4 11 4 8z" />
    <path d="M7.5 15.5a2 2 0 0 0 4 0" />
  </svg>
);
const CARD_BELL_ICON = (
  <svg width="15" height="15" viewBox="0 0 19 19" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 8a5.5 5.5 0 0 1 11 0c0 3 1 4 1.5 5H2.5C3 12 4 11 4 8z" />
    <path d="M7.5 15.5a2 2 0 0 0 4 0" />
  </svg>
);

// Ported from templates/_header.html's notification bell + panel,
// including the push-toggle row that used to live inside it.
export default function NotificationBell() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef(null);
  const push = usePushNotifications();

  useEffect(() => {
    function loadNotifications() {
      apiFetch("/api/notifications/recent")
        .then((res) => res.json())
        .then((data) => {
          setItems(data);
          let lastSeen = null;
          try { lastSeen = localStorage.getItem(LS_LAST_SEEN); } catch { /* ignore */ }
          const lastSeenIndex = lastSeen ? data.findIndex((n) => n.id === lastSeen) : -1;
          setUnreadCount(lastSeenIndex === -1 ? data.length : lastSeenIndex);
        })
        .catch(() => {});
    }
    // Fetched once on mount only before — a campaign sent while the tab
    // was already open (push notifications arrive live via Firebase, so
    // that side always looked immediate) never showed up here until a
    // full page reload. Poll instead, same cadence as the admin alert
    // tracker's own refresh.
    loadNotifications();
    const t = setInterval(loadNotifications, 60000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    function onDocClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  function onBellClick(e) {
    e.stopPropagation();
    setOpen((v) => !v);
    if (items.length) {
      try { localStorage.setItem(LS_LAST_SEEN, items[0].id); } catch { /* ignore */ }
      setUnreadCount(0);
    }
  }

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      <button type="button" aria-label="Notifications" onClick={onBellClick} style={{ background: "none", border: "none", cursor: "pointer", padding: "6px 8px", position: "relative", display: "flex", alignItems: "center", gap: 6 }}>
        {BELL_ICON}
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)" }}>Notification</span>
        {unreadCount > 0 && <span style={{ position: "absolute", top: 4, right: 2, width: 8, height: 8, borderRadius: "50%", background: "#E0473F" }} />}
      </button>
      {open && (
        <div style={{ position: "absolute", top: "100%", right: 0, marginTop: 8, width: "min(340px, 92vw)", maxHeight: "min(70vh, 520px)", overflowY: "auto", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "0 16px 32px rgba(20,23,31,0.14)", padding: 8, zIndex: 1000 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {!items.length ? (
              <div className="notif-card-empty">No notifications yet</div>
            ) : (
              items.map((n, i) => (
                <div key={n.id}>
                  <div className={"notif-card" + (i < unreadCount ? " notif-card-unread" : "")}>
                    <div className="notif-card-icon">{CARD_BELL_ICON}</div>
                    <div className="notif-card-body">
                      <div className="notif-card-top"><span className="notif-card-title">{n.title}</span><span className="notif-card-time">{timeAgo(n.sent_at)}</span></div>
                      <div className="notif-card-message">{linkify(n.body)}</div>
                    </div>
                  </div>
                  {i < items.length - 1 && <div className="notif-card-divider" />}
                </div>
              ))
            )}
          </div>
          {push.configured && (
            <div style={{ borderTop: "1px solid var(--border)", marginTop: 6, paddingTop: 6 }}>
              <label className="push-toggle-row" style={{ cursor: push.permissionDenied ? "default" : "pointer" }}>
                <span>
                  <span className="push-toggle-row-label">Push notifications</span>
                  <span className="push-toggle-row-sub">
                    {push.permissionDenied
                      ? "Blocked in your browser's site settings — enable notifications there, then reload"
                      : "New signals & account alerts"}
                  </span>
                </span>
                <span className="toggle-switch">
                  <input type="checkbox" checked={push.enabled} disabled={push.toggleDisabled} onChange={(e) => push.toggle(e.target.checked)} />
                  <span className="toggle-switch-track" />
                </span>
              </label>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
