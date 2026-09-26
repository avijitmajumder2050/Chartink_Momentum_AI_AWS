import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";

const LS_LAST_SEEN = "quantile_last_seen_campaign_chat";

// Same "[Label](https://...)" CTA convention as NotificationBell/Dashboard's
// own linkify — kept as its own copy since this widget doesn't import
// either of those.
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

function timeAgo(iso) {
  const diffMin = Math.max(0, Math.round((Date.now() - new Date(iso + "Z").getTime()) / 60000));
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 1440) return `${Math.round(diffMin / 60)}h ago`;
  return `${Math.round(diffMin / 1440)}d ago`;
}

const CHAT_ICON = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8">
    <path d="M4 5.5C4 4.7 4.7 4 5.5 4H18.5C19.3 4 20 4.7 20 5.5V14.5C20 15.3 19.3 16 18.5 16H9L5 19.5V16H5.5C4.7 16 4 15.3 4 14.5V5.5Z" strokeLinejoin="round" />
  </svg>
);
const CARD_CHAT_ICON = (
  <svg width="15" height="15" viewBox="0 0 19 19" fill="none" stroke="currentColor" strokeWidth="1.7">
    <path d="M3 4.5C3 3.7 3.7 3 4.5 3H14.5C15.3 3 16 3.7 16 4.5V11.5C16 12.3 15.3 13 14.5 13H7.5L4 16V13H4.5C3.7 13 3 12.3 3 11.5V4.5Z" strokeLinejoin="round" />
  </svg>
);

// Floating "channel chat" launcher for the subscriber dashboard: a chat
// bubble icon pinned to the bottom-right that badges/lights up whenever
// admin sends a new campaign, and opens to a chat-style feed of every
// campaign notification the viewer's plan is entitled to. Sits directly
// on top of the same feed NotificationBell already shows (GET /api/
// notifications/recent, already plan-filtered server-side) — no new
// backend endpoint, just a different, chat-shaped presentation of it,
// with its own independent read/unread state (LS_LAST_SEEN) so opening
// one of the two widgets doesn't silently clear the other's badge.
export default function CampaignChatWidget() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef(null);
  const listRef = useRef(null);

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
    // Same 60s polling cadence as NotificationBell — a campaign sent while
    // the dashboard is already open should still light this icon up
    // without needing a page reload.
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

  // Chat reads top-to-bottom, oldest first, like a conversation — the
  // opposite order from the bell's newest-first dropdown list.
  const chatItems = [...items].reverse();

  useEffect(() => {
    if (open && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [open, items]);

  function onToggle(e) {
    e.stopPropagation();
    setOpen((v) => !v);
    if (items.length) {
      try { localStorage.setItem(LS_LAST_SEEN, items[0].id); } catch { /* ignore */ }
      setUnreadCount(0);
    }
  }

  return (
    <div ref={panelRef} style={{ position: "fixed", right: 20, bottom: 20, zIndex: 1250 }}>
      {open && (
        <div className="chat-widget-panel">
          <div className="chat-widget-header">
            <span>Ask Chat</span>
            <button type="button" aria-label="Close" className="chat-widget-close" onClick={() => setOpen(false)}>×</button>
          </div>
          <div ref={listRef} className="chat-widget-list">
            {!chatItems.length ? (
              <div className="notif-card-empty">No campaign updates yet</div>
            ) : (
              chatItems.map((n, i) => (
                <div key={n.id}>
                  <div className="notif-card">
                    <div className="notif-card-icon">{CARD_CHAT_ICON}</div>
                    <div className="notif-card-body">
                      <div className="notif-card-top"><span className="notif-card-title">{n.title}</span><span className="notif-card-time">{timeAgo(n.sent_at)}</span></div>
                      <div className="notif-card-message">{linkify(n.body)}</div>
                    </div>
                  </div>
                  {i < chatItems.length - 1 && <div className="notif-card-divider" />}
                </div>
              ))
            )}
          </div>
        </div>
      )}
      <button type="button" aria-label="Admin campaign chat" className="chat-widget-btn" onClick={onToggle}>
        {CHAT_ICON}
        {unreadCount > 0 && <span className="chat-widget-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>}
      </button>
    </div>
  );
}
