import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const MARKETS_PATHS = ["/markets/ipo-hub", "/markets/research", "/scanner", "/markets/chart", "/markets/chart-wall"];

// Ported from templates/_header.html, now that every page it links to
// exists (Phase 4 completed the page set) — full nav including the
// Markets dropdown, restored from Phase 1's deliberately reduced version.
export default function Header() {
  const { user, loading, login, logout } = useAuth();
  const location = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const marketsActive = MARKETS_PATHS.some((p) => location.pathname === p || location.pathname.startsWith(p + "?"));

  useEffect(() => {
    function onDocClick(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setDropdownOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setDropdownOpen(false);
    }
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const navLinkClass = ({ isActive }) => "site-nav-link" + (isActive ? " active" : "");

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <div className="site-header-left">
          <Link className="brand" to="/">
            <span className="brand-mark">
              <svg width="18" height="18" viewBox="0 0 30 30" fill="none">
                <path d="M7 20L12.5 12.5L16.5 17L23 8" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M18 8H23V13" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            Quantile
          </Link>
          <nav className="site-nav">
            <NavLink to="/" className={navLinkClass} end>Home</NavLink>
            <NavLink to="/news" className={navLinkClass}>News</NavLink>
            <NavLink to="/capabilities" className={navLinkClass}>Capabilities</NavLink>
            <div className="site-nav-dropdown" ref={dropdownRef}>
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
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <Link to="/subscription" style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)" }}>{user.name}</Link>
              <button type="button" onClick={logout} className="site-login-link" style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit" }}>
                Log out
              </button>
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
