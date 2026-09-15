import { Link } from "react-router-dom";

// Ported from templates/pricing.html. Static-in-React — plan prices/
// features here mirror subscription_connector.PLANS's real price_paise
// values (₹0/₹499/₹1,299), the rest (comparison rows, FAQs) is
// illustrative marketing copy from mock_data.py's pricing_data().
const PLANS = [
  {
    name: "Free", tagline: "Get a feel for the market", price: "₹0", period: "/ forever", cardBg: "#FFFFFF", border: "1px solid #E3E6EC",
    titleColor: "#14171F", subColor: "#5B6270", ctaBg: "#F0F1F4", ctaColor: "#14171F", cta: "Current plan", checkBg: "#E9EAF0", checkColor: "#5B6270", featured: false,
    features: ["Delayed market quotes (15 min)", "IPO calendar, no GMP alerts", "5 stocks in watchlist", "Markets 101 course track", "Community forum access"],
  },
  {
    name: "Pro", tagline: "For active retail investors", price: "₹499", period: "/ month", cardBg: "#14171F", border: "2px solid #4640DE",
    titleColor: "#FFFFFF", subColor: "#9297A8", ctaBg: "#4640DE", ctaColor: "#FFFFFF", cta: "Start 7-day free trial", checkBg: "#2A2E3A", checkColor: "#4ADE9C", featured: true,
    features: ["Real-time NSE/BSE quotes", "Live GMP tracking & alerts", "Unlimited watchlist", "Full technical scanner", "All 6 course tracks", "Weekly live webinars"],
  },
  {
    name: "Premium", tagline: "For serious traders & analysts", price: "₹1,299", period: "/ month", cardBg: "#FFFFFF", border: "1px solid #E3E6EC",
    titleColor: "#14171F", subColor: "#5B6270", ctaBg: "#FBF2E1", ctaColor: "#B98A2E", cta: "Start 7-day free trial", checkBg: "#FBF2E1", checkColor: "#B98A2E", featured: false,
    features: ["Everything in Pro", "Advanced options screener", "Peer & sector deep research", "Priority support (15 min SLA)", "1-on-1 quarterly strategy call", "API access for your own tools"],
  },
];
const COMPARISON_ROWS = [
  { label: "Market data delay", free: "15 min", pro: "Real-time", premium: "Real-time" },
  { label: "IPO GMP alerts", free: "—", pro: "Yes", premium: "Yes" },
  { label: "Scanner filters", free: "3", pro: "40+", premium: "40+ & custom" },
  { label: "Watchlist size", free: "5 stocks", pro: "Unlimited", premium: "Unlimited" },
  { label: "Chart indicators", free: "3", pro: "30+", premium: "30+" },
  { label: "Course tracks", free: "1", pro: "6", premium: "6 + workshops" },
  { label: "Support", free: "Community", pro: "Email, 24h", premium: "Priority, 15 min" },
];
const FAQS = [
  { q: "Is Quantile a SEBI-registered advisor?", a: "No. Quantile is a research and analytics platform. Data, scores and screeners are for informational purposes only and are not investment advice." },
  { q: "Can I cancel my subscription anytime?", a: "Yes, cancel from your account settings anytime — you keep access until the end of the billing period, no questions asked." },
  { q: "What payment methods do you accept?", a: "UPI, all major debit/credit cards, and net banking through our RBI-compliant payment partner." },
  { q: "Do you offer a student or annual discount?", a: "Annual billing saves 20% versus monthly. Verified students get an additional 15% off Pro with a valid .edu or college ID." },
  { q: "Is my payment and personal data secure?", a: "Yes — payments are processed by a PCI-DSS compliant gateway; we never store your card details on Quantile servers." },
];

export default function Pricing() {
  return (
    <>
      <div style={{ width: "100%", padding: "72px clamp(16px, 5vw, 48px) 0", textAlign: "center" }}>
        <div style={{ maxWidth: 620, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14, alignItems: "center" }}>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Pricing</span>
          <h1 style={{ fontSize: 38, fontWeight: 800, letterSpacing: "-0.02em" }}>Plans for every stage of investing</h1>
          <p style={{ fontSize: 16, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>Start free. Upgrade when the scanner and live charts start paying for themselves.</p>
          <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 100, padding: 5, marginTop: 10 }}>
            <span style={{ fontSize: 13.5, fontWeight: 700, color: "white", background: "#14171F", padding: "8px 18px", borderRadius: 100 }}>Monthly</span>
            <span style={{ fontSize: 13.5, fontWeight: 600, color: "#5B6270", padding: "8px 18px", display: "flex", alignItems: "center", gap: 6 }}>
              Annual <span style={{ fontSize: 11, fontWeight: 700, color: "#17A673", background: "#E6F7F1", padding: "2px 7px", borderRadius: 100 }}>Save 20%</span>
            </span>
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "44px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1120, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20, alignItems: "start" }}>
          {PLANS.map((p) => (
            <div key={p.name} style={{ background: p.cardBg, border: p.border, borderRadius: 20, padding: 32, display: "flex", flexDirection: "column", gap: 18, position: "relative" }}>
              {p.featured && (
                <span style={{ position: "absolute", top: -13, left: 32, background: "#F2A93B", color: "#14171F", fontSize: 11.5, fontWeight: 700, padding: "5px 12px", borderRadius: 100 }}>Most popular</span>
              )}
              <div>
                <span style={{ fontSize: 15, fontWeight: 700, color: p.titleColor }}>{p.name}</span>
                <p style={{ fontSize: 13, color: p.subColor, marginTop: 4, minHeight: 34 }}>{p.tagline}</p>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span className="num" style={{ fontSize: 38, fontWeight: 800, color: p.titleColor }}>{p.price}</span>
                <span style={{ fontSize: 13.5, color: p.subColor }}>{p.period}</span>
              </div>
              <Link to="/subscription" style={{ background: p.ctaBg, color: p.ctaColor, textAlign: "center", fontSize: 14, fontWeight: 700, padding: "13px 0", borderRadius: 10, display: "block" }}>{p.cta}</Link>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 6 }}>
                {p.features.map((f) => (
                  <div key={f} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, marginTop: 2 }}>
                      <circle cx="8" cy="8" r="8" fill={p.checkBg} /><path d="M4.5 8.2L6.8 10.5L11.5 5.5" stroke={p.checkColor} strokeWidth="1.6" fill="none" />
                    </svg>
                    <span style={{ fontSize: 13.5, color: p.subColor }}>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ width: "100%", padding: "80px clamp(16px, 5vw, 48px) 0" }}>
        <div style={{ maxWidth: 1120, margin: "0 auto" }}>
          <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 22 }}>Compare all features</h2>
          <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, overflow: "hidden" }}>
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", padding: "16px 24px", background: "#FAF9F6", borderBottom: "1px solid #E3E6EC" }}>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "#8A90A0", textTransform: "uppercase", letterSpacing: "0.04em" }}>Feature</span>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "#8A90A0", textAlign: "center" }}>Free</span>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "#4640DE", textAlign: "center" }}>Pro</span>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "#B98A2E", textAlign: "center" }}>Premium</span>
            </div>
            {COMPARISON_ROWS.map((row) => (
              <div key={row.label} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", padding: "15px 24px", borderBottom: "1px solid #F0F1F4", alignItems: "center" }}>
                <span style={{ fontSize: 13.5, color: "#33374A" }}>{row.label}</span>
                <span style={{ textAlign: "center", fontSize: 13, color: "#8A90A0" }}>{row.free}</span>
                <span style={{ textAlign: "center", fontSize: 13, fontWeight: 600, color: "#4640DE" }}>{row.pro}</span>
                <span style={{ textAlign: "center", fontSize: 13, fontWeight: 600, color: "#B98A2E" }}>{row.premium}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", padding: "72px clamp(16px, 5vw, 48px) 88px" }}>
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 26, textAlign: "center" }}>Frequently asked questions</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {FAQS.map((q) => (
              <div key={q.q} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 14, padding: "20px 22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 14.5, fontWeight: 700 }}>{q.q}</span>
                  <span style={{ fontSize: 18, color: "#8A90A0" }}>+</span>
                </div>
                <p style={{ fontSize: 13.5, color: "#5B6270", lineHeight: 1.65, margin: "10px 0 0" }}>{q.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
