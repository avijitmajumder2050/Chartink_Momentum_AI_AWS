import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Deliberately a reduced nav for now — only routes that actually exist in
// the React app get a link (just Capabilities in Phase 1). The full nav
// from templates/_header.html (News, Markets dropdown, Education,
// Pricing, Dashboard, Admin, the notification bell) gets filled back in
// page-by-page as each is ported in later phases (see the rewrite plan) —
// linking to a page that isn't built yet would just be a dead link.
export default function Header() {
  const { user, loading, login, logout } = useAuth();

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
            <NavLink to="/" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")} end>
              Home
            </NavLink>
            <NavLink to="/news" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              News
            </NavLink>
            <NavLink to="/capabilities" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              Capabilities
            </NavLink>
            <NavLink to="/markets/ipo-hub" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              IPO Hub
            </NavLink>
            <NavLink to="/markets/research" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              Research
            </NavLink>
            <NavLink to="/scanner" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              Scanner
            </NavLink>
            <NavLink to="/markets/chart" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              Chart
            </NavLink>
            <NavLink to="/markets/chart-wall" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
              Chart Wall
            </NavLink>
            {user && (
              <NavLink to="/dashboard" className={({ isActive }) => "site-nav-link" + (isActive ? " active" : "")}>
                Dashboard
              </NavLink>
            )}
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
