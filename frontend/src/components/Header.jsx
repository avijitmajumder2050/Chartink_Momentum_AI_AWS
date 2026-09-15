import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import NotificationBell from "./NotificationBell";

const MARKETS_PATHS = ["/markets/ipo-hub", "/markets/research", "/scanner", "/markets/chart", "/markets/chart-wall"];

function UserMenu({ user, logout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        aria-label="Account"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}
      >
        <span className="user-avatar">{(user.name?.[0] || user.email[0]).toUpperCase()}</span>
      </button>
      {open && (
        <div style={{ position: "absolute", top: "100%", right: 0, marginTop: 8, width: 220, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "0 16px 32px rgba(20,23,31,0.14)", padding: 6, zIndex: 1000 }}>
          <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", marginBottom: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", overflowWrap: "anywhere" }}>{user.name}</div>
            <div style={{ fontSize: 11.5, color: "var(--text-faint)", overflowWrap: "anywhere", marginTop: 2 }}>{user.email}</div>
          </div>
          <Link to="/dashboard" onClick={() => setOpen(false)} style={{ display: "block", padding: "8px 12px", fontSize: 13, fontWeight: 600, color: "var(--text)", borderRadius: 8 }}>
            Account details
          </Link>
          <button
            type="button"
            onClick={logout}
            style={{ width: "100%", textAlign: "left", padding: "8px 12px", fontSize: 13, fontWeight: 600, color: "var(--down)", background: "none", border: "none", cursor: "pointer", borderRadius: 8, fontFamily: "inherit" }}
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

// Ported from templates/_header.html, now that every page it links to
// exists (Phase 4 completed the page set) — full nav including the
// Markets dropdown, restored from Phase 1's deliberately reduced version.
export default function Header() {
  const { user, loading, login, logout } = useAuth();
  const location = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const dropdownRef = useRef(null);

  const marketsActive = MARKETS_PATHS.some((p) => location.pathname === p || location.pathname.startsWith(p + "?"));

  const mobileNavRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setDropdownOpen(false);
      if (mobileNavRef.current && !mobileNavRef.current.contains(e.target)) setMobileNavOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") {
        setDropdownOpen(false);
        setMobileNavOpen(false);
      }
    }
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  // A route change (nav link tap, or the browser back/forward buttons)
  // should always close the mobile menu — otherwise it stays open,
  // covering the page you just navigated to.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const navLinkClass = ({ isActive }) => "site-nav-link" + (isActive ? " active" : "");

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <div className="site-header-left" ref={mobileNavRef}>
          <Link className="brand" to="/">
            <span className="brand-mark">
              <svg width="18" height="18" viewBox="0 0 30 30" fill="none">
                <path d="M7 20L12.5 12.5L16.5 17L23 8" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M18 8H23V13" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            Quantile
          </Link>
          <button
            type="button"
            className="site-nav-toggle"
            aria-label={mobileNavOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileNavOpen}
            onClick={(e) => {
              e.stopPropagation();
              setMobileNavOpen((v) => !v);
            }}
          >
            {mobileNavOpen ? (
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M5 5L17 17M17 5L5 17" /></svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M3 6H19M3 11H19M3 16H19" /></svg>
            )}
          </button>
          <nav className={"site-nav" + (mobileNavOpen ? " mobile-open" : "")}>
            <NavLink to="/" className={navLinkClass} end>Home</NavLink>
            <NavLink to="/news" className={navLinkClass}>News</NavLink>
            <NavLink to="/capabilities" className={navLinkClass}>Capabilities</NavLink>
            <div className={"site-nav-dropdown" + (dropdownOpen ? " open" : "")} ref={dropdownRef}>
              <button
                type="button"
                className={"site-nav-link site-nav-dropdown-trigger" + (marketsActive ? " active" : "")}
                aria-haspopup="true"
                aria-expanded={dropdownOpen}
                onClick={(e) => {
                  e.stopPropagation();
                  setDropdownOpen((v) => !v);
                }}
              >
                Markets
                <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2.5 4L5.5 7L8.5 4" /></svg>
              </button>
              {dropdownOpen && (
                <div className="site-nav-dropdown-menu">
                  <div className="site-nav-dropdown-menu-inner">
                    <Link to="/markets/ipo-hub" onClick={() => setDropdownOpen(false)}>IPO Hub</Link>
                    <Link to="/markets/research" onClick={() => setDropdownOpen(false)}>Stock Research</Link>
                    <Link to="/scanner" onClick={() => setDropdownOpen(false)}>Scanner</Link>
                    <Link to="/markets/chart" onClick={() => setDropdownOpen(false)}>Chart</Link>
                    <Link to="/markets/chart-wall" onClick={() => setDropdownOpen(false)}>Chart Wall</Link>
                  </div>
                </div>
              )}
            </div>
            <NavLink to="/education" className={navLinkClass}>Education</NavLink>
            <NavLink to="/pricing" className={navLinkClass}>Pricing</NavLink>
            {user && <NavLink to="/dashboard" className={navLinkClass}>Dashboard</NavLink>}
            {user?.role === "admin" && <NavLink to="/admin" className={navLinkClass}>Admin</NavLink>}
          </nav>
        </div>
        <div className="site-header-right">
          {loading ? null : user ? (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <NotificationBell />
              <UserMenu user={user} logout={logout} />
            </div>
          ) : (
            <>
              <button type="button" onClick={login} className="site-login-link" style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit" }}>
                Log in
              </button>
              <button type="button" onClick={login} className="site-cta-btn" style={{ border: "none", cursor: "pointer", fontFamily: "inherit" }}>
                Get Started Free
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
