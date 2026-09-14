import { Link } from "react-router-dom";

// Ported from templates/_footer.html. Links to pages not yet built in the
// SPA stay "#" for now (same placeholder convention _footer.html itself
// already used for Webinars/Glossary/Blog/legal pages) — swapped for real
// <Link>s as each page is ported in later phases.
export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-top">
        <div className="site-footer-brand">
          <div className="brand" style={{ color: "white" }}>
            <span className="brand-mark">
              <svg width="16" height="16" viewBox="0 0 30 30" fill="none">
                <path d="M7 20L12.5 12.5L16.5 17L23 8" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M18 8H23V13" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            Quantile
          </div>
          <p>Research, scan and track NSE &amp; BSE markets in one place. Built for Indian retail investors, from first SIP to serious swing trades.</p>
        </div>
        <div className="site-footer-cols">
          <div className="site-footer-col">
            <span className="site-footer-col-title">Product</span>
            <a href="#">IPO Hub</a>
            <a href="#">Stock Research</a>
            <a href="#">Scanner</a>
            <a href="#">Charts</a>
            <a href="#">News</a>
          </div>
          <div className="site-footer-col">
            <span className="site-footer-col-title">Learn</span>
            <a href="#">Education</a>
            <a href="#">Webinars</a>
            <a href="#">Glossary</a>
            <a href="#">Blog</a>
          </div>
          <div className="site-footer-col">
            <span className="site-footer-col-title">Company</span>
            <a href="#">Vision</a>
            <Link to="/capabilities">Capabilities</Link>
            <a href="#">Pricing</a>
            <a href="#">Careers</a>
            <a href="#">Contact</a>
          </div>
          <div className="site-footer-col">
            <span className="site-footer-col-title">Legal</span>
            <a href="#">Privacy Policy</a>
            <a href="#">Terms of Use</a>
            <a href="#">Refund Policy</a>
            <a href="#">Grievance</a>
          </div>
        </div>
      </div>
      <div className="site-footer-bottom">
        <p>
          Quantile is a research and analytics platform, not a SEBI-registered investment adviser or broker. Content on this platform, including IPO data,
          screeners, scores and charts, is for educational and informational purposes only and does not constitute investment advice. Investments in
          securities are subject to market risk; please read all scheme-related documents carefully. Past performance is not indicative of future returns.
        </p>
        <div className="site-footer-legal-row">
          <span>© 2026 Quantile Technologies Pvt. Ltd. All rights reserved.</span>
          <span>CIN: U67190MH2026PTC000000 · Mumbai, India</span>
        </div>
      </div>
    </footer>
  );
}
