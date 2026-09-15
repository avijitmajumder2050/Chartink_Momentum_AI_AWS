import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

// Ported from templates/subscription.html. New GET /api/subscription/
// bootstrap (app.py) replaces the bootstrap data that used to be inline
// in subscription_page(); checkout/checkout-confirm/cancel/redeem-
// voucher (already JSON) are called with the exact same snake_case
// field names the original page's JS used (razorpay_subscription_id
// etc.) — that's the real Razorpay API contract, not a convention worth
// reformatting.

function postJson(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) }).then((res) =>
    res.json().then((data) => ({ ok: res.ok, data }))
  );
}

export default function Subscription() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [bootstrapError, setBootstrapError] = useState(false);
  const [message, setMessage] = useState(null); // {text, isError}
  const [voucherPlan, setVoucherPlan] = useState("pro");
  const [voucherCode, setVoucherCode] = useState("");
  const [busyPlan, setBusyPlan] = useState(null);
  const razorpayLoaded = useRef(false);
  const voucherFormRef = useRef(null);

  const loadBootstrap = useCallback(() => {
    setBootstrapError(false);
    return apiFetch("/api/subscription/bootstrap")
      .then((res) => res.json())
      .then(setData)
      .catch(() => setBootstrapError(true));
  }, []);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  useEffect(() => {
    if (!data?.razorpay?.configured || razorpayLoaded.current) return;
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    document.body.appendChild(script);
    razorpayLoaded.current = true;
  }, [data]);

  function showMessage(text, isError) {
    setMessage({ text, isError });
  }

  function submitVoucher(e) {
    e.preventDefault();
    postJson("/api/subscription/redeem-voucher", { plan: voucherPlan, code: voucherCode }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't apply that voucher.", true);
        return;
      }
      if (result.data.requiresCheckout) {
        if (!data.razorpay.keyId) {
          showMessage(
            `This voucher is ${result.data.percentOff}% off, which needs card/UPI checkout — that isn't set up yet. Ask for a 100%-off code instead.`,
            true
          );
          return;
        }
        showMessage(`Applying ${result.data.percentOff}% off — complete checkout to activate.`, false);
        startCheckout(voucherPlan, voucherCode);
        return;
      }
      showMessage(`Voucher applied — you're on ${result.data.subscription.plan} now.`, false);
      setTimeout(loadBootstrap, 1200);
    });
  }

  function cancelSubscription() {
    if (!window.confirm("Cancel your subscription? You'll keep access until the end of the current period.")) return;
    postJson("/api/subscription/cancel", {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't cancel.", true);
        return;
      }
      showMessage("Subscription canceled — you'll keep access until the period ends.", false);
      setTimeout(loadBootstrap, 1200);
    });
  }

  function downgradeToFree() {
    if (!window.confirm("Switch to the Free plan? You'll keep paid access until the end of the current period, then move to Free.")) return;
    postJson("/api/subscription/cancel", {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't switch plans.", true);
        return;
      }
      showMessage("You'll move to Free at the end of the current period.", false);
      setTimeout(loadBootstrap, 1200);
    });
  }

  function startCheckout(plan, code, onDone) {
    postJson("/api/subscription/checkout", { plan, code: code || undefined }).then((result) => {
      if (onDone) onDone();
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't start checkout.", true);
        return;
      }

      const rzp = new window.Razorpay({
        key: result.data.razorpay_key_id,
        subscription_id: result.data.razorpay_subscription_id,
        name: "Quantile",
        description: `Quantile ${plan}`,
        prefill: { email: user?.email, name: user?.name },
        handler: (response) => {
          postJson("/api/subscription/checkout/confirm", {
            plan,
            code: code || undefined,
            razorpay_subscription_id: response.razorpay_subscription_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          }).then((confirmResult) => {
            if (!confirmResult.ok) {
              showMessage(confirmResult.data.error || "Payment succeeded but activation failed — contact support.", true);
              return;
            }
            showMessage(`You're subscribed to ${plan}!`, false);
            setTimeout(loadBootstrap, 1200);
          });
        },
      });
      rzp.open();
    });
  }

  function onSubscribeClick(planId) {
    setBusyPlan(planId);
    startCheckout(planId, null, () => setBusyPlan(null));
  }

  function applyCampaign(code, plan) {
    setVoucherPlan(plan);
    setVoucherCode(code);
    voucherFormRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  if (bootstrapError) {
    return (
      <div style={{ width: "100%", padding: "80px 40px", textAlign: "center" }}>
        <p style={{ fontSize: 14, color: "#5B6270", marginBottom: 14 }}>We couldn't load your subscription right now. Please try again.</p>
        <button
          type="button"
          onClick={loadBootstrap}
          style={{ background: "#4640DE", color: "white", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 700, padding: "10px 20px", borderRadius: 9 }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ width: "100%", padding: "80px 40px", textAlign: "center", fontSize: 13, color: "#8A90A0" }}>
        Loading your subscription…
      </div>
    );
  }
  const { subscription: sub, plans, campaigns, razorpay } = data;

  return (
    <div style={{ width: "100%", padding: "clamp(24px, 6vw, 48px) clamp(16px, 5vw, 48px) 90px" }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <div style={{ marginBottom: 28 }}>
          <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Account</span>
          <h1 style={{ fontSize: 28, fontWeight: 800, marginTop: 6 }}>Your subscription</h1>
        </div>

        <div style={{ background: "#14171F", borderRadius: 18, padding: 28, marginBottom: 32, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
          <div>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#9297A8", letterSpacing: "0.04em", textTransform: "uppercase" }}>Current plan</span>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
              <span style={{ fontSize: 24, fontWeight: 800, color: "white" }}>{sub.plan_details.name}</span>
              {sub.status === "active" && (
                <span style={{ fontSize: 11, fontWeight: 700, color: "#4ADE9C", background: "rgba(74,222,156,0.12)", padding: "3px 9px", borderRadius: 100 }}>Active</span>
              )}
              {sub.status === "canceled" && (
                <span style={{ fontSize: 11, fontWeight: 700, color: "#F2A93B", background: "rgba(242,169,59,0.12)", padding: "3px 9px", borderRadius: 100 }}>Cancels at period end</span>
              )}
              {sub.status === "past_due" && (
                <span style={{ fontSize: 11, fontWeight: 700, color: "#E0473F", background: "rgba(224,71,63,0.12)", padding: "3px 9px", borderRadius: 100 }}>Payment failed</span>
              )}
            </div>
            {sub.current_period_end && (
              <p style={{ fontSize: 12.5, color: "#9297A8", margin: "8px 0 0" }}>
                {sub.status === "canceled" ? "Access until" : "Renews"} {sub.current_period_end.slice(0, 10)}
              </p>
            )}
            {sub.voucher_code && (
              <p style={{ fontSize: 12.5, color: "#9297A8", margin: "4px 0 0" }}>
                Activated with voucher <strong style={{ color: "white" }}>{sub.voucher_code}</strong>
              </p>
            )}
          </div>
          {sub.plan !== "free" && sub.status === "active" && (
            <button type="button" onClick={cancelSubscription} style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "none", fontSize: 13, fontWeight: 700, padding: "11px 20px", borderRadius: 9, cursor: "pointer" }}>
              Cancel subscription
            </button>
          )}
        </div>

        {message && (
          <div style={{ fontSize: 13, fontWeight: 600, padding: "11px 14px", borderRadius: 10, marginBottom: 20, background: message.isError ? "#FDEDEC" : "#EAF7F1", color: message.isError ? "#C0392B" : "#17A673" }}>
            {message.text}
          </div>
        )}

        {campaigns.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
            {campaigns.map((c) => (
              <div key={c.code} style={{ background: "#FBF2E1", border: "1px solid #F2D9A0", borderRadius: 12, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <span style={{ fontSize: 13.5, color: "#7A5B10" }}>
                  🎉 <strong>{c.name}</strong> — use code <strong style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{c.code}</strong> for {c.percent_off}% off{" "}
                  {c.applicable_plans.join(" or ").replace(/^\w/, (ch) => ch.toUpperCase())}
                </span>
                <button
                  type="button"
                  onClick={() => applyCampaign(c.code, c.applicable_plans[0])}
                  style={{ background: "#B98A2E", color: "white", border: "none", fontSize: 12.5, fontWeight: 700, padding: "8px 16px", borderRadius: 8, cursor: "pointer" }}
                >
                  Apply
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 18 }}>
          {Object.entries(plans).map(([planId, plan]) => (
            <div key={planId} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <span style={{ fontSize: 15, fontWeight: 700 }}>{plan.name}</span>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 6 }}>
                  <span className="num" style={{ fontSize: 26, fontWeight: 800 }}>₹{Math.floor(plan.price_paise / 100)}</span>
                  {plan.period && <span style={{ fontSize: 12.5, color: "#8A90A0" }}>/ {plan.period}</span>}
                </div>
              </div>

              {sub.plan === planId && sub.status !== "canceled" ? (
                <button type="button" disabled style={{ background: "#F0F1F4", color: "#8A90A0", border: "none", fontSize: 13.5, fontWeight: 700, padding: "12px 0", borderRadius: 9, cursor: "not-allowed" }}>
                  Current plan
                </button>
              ) : planId === "free" ? (
                <button type="button" onClick={downgradeToFree} style={{ background: "#F0F1F4", color: "#14171F", border: "none", fontSize: 13.5, fontWeight: 700, padding: "12px 0", borderRadius: 9, cursor: "pointer" }}>
                  Switch to Free
                </button>
              ) : razorpay.configured ? (
                <button
                  type="button"
                  disabled={busyPlan === planId}
                  onClick={() => onSubscribeClick(planId)}
                  style={{ background: "#4640DE", color: "white", border: "none", fontSize: 13.5, fontWeight: 700, padding: "12px 0", borderRadius: 9, cursor: "pointer" }}
                >
                  Subscribe
                </button>
              ) : (
                <span style={{ fontSize: 12, color: "#8A90A0", textAlign: "center" }}>Card/UPI checkout coming soon — use a voucher below</span>
              )}
            </div>
          ))}
        </div>

        <div ref={voucherFormRef} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 24, marginTop: 24 }}>
          <span style={{ fontSize: 14, fontWeight: 700, display: "block", marginBottom: 14 }}>Have a voucher code?</span>
          <form onSubmit={submitVoucher} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <select value={voucherPlan} onChange={(e) => setVoucherPlan(e.target.value)} style={{ border: "1.5px solid #E3E6EC", borderRadius: 10, padding: "11px 12px", fontSize: 13.5, background: "white" }}>
              <option value="pro">Pro</option>
              <option value="premium">Premium</option>
            </select>
            <input
              type="text"
              required
              value={voucherCode}
              onChange={(e) => setVoucherCode(e.target.value)}
              placeholder="Voucher code"
              style={{ flex: 1, minWidth: 160, border: "1.5px solid #E3E6EC", borderRadius: 10, padding: "11px 14px", fontSize: 13.5 }}
            />
            <button type="submit" style={{ background: "#14171F", color: "white", border: "none", fontSize: 13.5, fontWeight: 700, padding: "12px 22px", borderRadius: 9, cursor: "pointer" }}>
              Apply
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
