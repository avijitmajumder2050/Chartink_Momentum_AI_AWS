import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import useIsMobile from "../hooks/useIsMobile";

// Ported from templates/_admin_sidebar.html. NAV_ITEMS mirrors
// app.py's ADMIN_NAV_ITEMS, with React paths instead of Flask endpoint
// names for url_for().
const NAV_ITEMS = [
  { label: "Overview", to: "/admin", end: true },
  { label: "Users", to: "/admin/users" },
  { label: "Subscriptions", to: "/admin/subscriptions" },
  { label: "Voucher Campaigns", to: "/admin/campaigns" },
  { label: "Scanner Campaign", to: "/admin/scanner-campaign" },
  { label: "IPO Data", to: "/markets/ipo-hub" },
  { label: "Courses", to: "/education" },
];

export default function AdminSidebar() {
  const { user } = useAuth();
  const isMobile = useIsMobile();

  // A 232px full-height vertical block works fine next to content on
  // desktop, but on a phone it either eats the whole screen (if kept
  // full-height) or squeezes the page into a sliver (if kept full-width
  // AND full-height side by side) — collapse to a horizontal
  // scrollable tab strip instead, same nav items, no page/user footer.
  if (isMobile) {
    return (
      <div style={{ background: "#14171F", padding: "10px 12px", display: "flex", gap: 6, overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
        {NAV_ITEMS.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            style={({ isActive }) => ({
              display: "flex", alignItems: "center", padding: "8px 14px", borderRadius: 8,
              background: isActive ? "#1F2330" : "transparent", textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0,
            })}
          >
            {({ isActive }) => (
              <span style={{ fontSize: 12.5, fontWeight: isActive ? 700 : 500, color: isActive ? "#FFFFFF" : "#9297A8" }}>{n.label}</span>
            )}
          </NavLink>
        ))}
      </div>
    );
  }

  return (
    <div style={{ width: 232, flexShrink: 0, background: "#14171F", minHeight: "100vh", padding: "22px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 10px 22px" }}>
        <svg width="24" height="24" viewBox="0 0 30 30" fill="none">
          <rect width="30" height="30" rx="8" fill="#4640DE" />
          <path d="M7 20L12.5 12.5L16.5 17L23 8" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M18 8H23V13" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span style={{ fontFamily: "'Manrope', sans-serif", fontWeight: 800, fontSize: 16, color: "white" }}>
          Quantile <span style={{ color: "#9297A8", fontWeight: 600, fontSize: 12 }}>Admin</span>
        </span>
      </div>
      {NAV_ITEMS.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.end}
          style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 11, padding: "10px 12px", borderRadius: 9,
            background: isActive ? "#1F2330" : "transparent", textDecoration: "none",
          })}
        >
          {({ isActive }) => (
            <>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke={isActive ? "#FFFFFF" : "#9297A8"} strokeWidth="1.6">
                <rect x="2" y="2" width="12" height="12" rx="2.5" />
              </svg>
              <span style={{ fontSize: 13.5, fontWeight: isActive ? 700 : 500, color: isActive ? "#FFFFFF" : "#9297A8" }}>{n.label}</span>
            </>
          )}
        </NavLink>
      ))}
      <div style={{ flex: 1 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 12, borderTop: "1px solid #2A2E3A", marginTop: 10 }}>
        <div style={{ width: 30, height: 30, borderRadius: "50%", background: "#4640DE", color: "white", fontWeight: 700, fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {user.name.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ minWidth: 0 }}>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: "white", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</span>
          <span style={{ fontSize: 11, color: "#8A90A0" }}>Admin</span>
        </div>
      </div>
    </div>
  );
}
