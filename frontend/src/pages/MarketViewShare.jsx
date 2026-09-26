import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../api/client";

// Admin-only "Share market view" panel for the Sector Overview Day view.
// Draws a 1080×1350 share card on a <canvas> from the live Day view data
// and offers: Copy image (clipboard), Download PNG, an editable text
// summary (Copy text), and Send — which pushes the TEXT to subscribers
// in-app + push via POST /api/admin/market-view/send. By design the image
// is never uploaded or stored anywhere: it only exists in this browser
// until the admin pastes it where they share.

const CARD_W = 1080;
const CARD_H = 1350;
const CARD_STOCKS = 4; // per side; fills the card's bottom half
const C = {
  bg: "#0F131C",
  card: "#161B27",
  border: "#262C3A",
  text: "#F4F5F8",
  text2: "#A6ACBB",
  muted: "#6F7687",
  up: "#4ADE9C",
  down: "#F87171",
  accent: "#4640DE",
};
const FONT = `"Manrope", "Segoe UI", Arial, sans-serif`;
const NUM_FONT = `"IBM Plex Sans", "Segoe UI", Arial, sans-serif`;
const AUDIENCES = [
  { key: "pro", label: "Pro" },
  { key: "premium", label: "Premium" },
  { key: "free", label: "Free" },
];

const fmt = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const signed = (n, d = 2) => {
  if (n == null) return "—";
  const r = Number(n.toFixed(d));
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${fmt(Math.abs(r), d)}`;
};
const shortSector = (name) => {
  const s = name.replace(/^Nifty\s+/i, "");
  return { "Financial Services": "Fin. Services", "Consumer Durables": "Cons. Durables", Infrastructure: "Infra" }[s] || s;
};

// ---------------------------------------------------------------------
// Model: everything the card + caption show, from the Day view payload.
// ---------------------------------------------------------------------
function buildMarketView(data, tiles, stocks) {
  const by = Object.fromEntries((data?.indices || []).map((r) => [r.symbol, r]));
  const sorted = [...(tiles || [])].filter((t) => t.changePct != null).sort((a, b) => b.changePct - a.changePct);
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  const bestStocks = best ? (stocks?.[best.symbol] || []).slice(0, CARD_STOCKS) : [];
  const worstStocks = worst ? [...(stocks?.[worst.symbol] || [])].reverse().slice(0, CARD_STOCKS) : [];
  const at = data?.updatedAt ? new Date(data.updatedAt) : new Date();
  return {
    at,
    live: !!data?.marketOpen,
    indices: [by.NIFTY, by.SENSEX, by.BANKNIFTY].filter(Boolean).map((r) => ({ label: r.name.replace(/^Nifty 50$/i, "NIFTY 50").replace(/^Nifty Bank$/i, "BANK NIFTY").replace(/^Sensex$/i, "SENSEX"), value: r.close, change: r.change, pct: r.changePct })),
    vix: by["INDIA VIX"] ? { value: by["INDIA VIX"].close, pct: by["INDIA VIX"].changePct } : null,
    breadth: data?.breadth?.sampleSize ? data.breadth : null,
    topSectors: sorted.slice(0, 3),
    bottomSectors: sorted.slice(-3).reverse(),
    best,
    worst,
    bestStocks,
    worstStocks,
  };
}

const istDate = (d) => d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
const istTime = (d) => d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });

function buildCaption(m, url) {
  const lines = [`📊 Quantile market view — ${istDate(m.at)}, ${istTime(m.at)} IST${m.live ? " (live)" : " (after close)"}`];
  if (m.indices.length) lines.push(m.indices.map((i) => `${i.label} ${fmt(i.value)} (${signed(i.pct)}%)`).join(" · "));
  const extra = [];
  if (m.breadth) extra.push(`Breadth: ${m.breadth.advancing} advancing / ${m.breadth.declining} declining`);
  if (m.vix) extra.push(`India VIX ${fmt(m.vix.value)}`);
  if (extra.length) lines.push(extra.join(" · "));
  if (m.best) {
    const s = m.bestStocks.slice(0, 2).map((x) => `${x.symbol} ${signed(x.changePct)}%`).join(", ");
    lines.push(`▲ Strongest: ${shortSector(m.best.name)} ${signed(m.best.changePct)}%${s ? ` — ${s}` : ""}`);
  }
  if (m.worst && m.worst !== m.best) {
    const s = m.worstStocks.slice(0, 2).map((x) => `${x.symbol} ${signed(x.changePct)}%`).join(", ");
    lines.push(`▼ Weakest: ${shortSector(m.worst.name)} ${signed(m.worst.changePct)}%${s ? ` — ${s}` : ""}`);
  }
  lines.push(`Sector view: ${url}`);
  lines.push("Market data summary, not investment advice.");
  return lines.join("\n");
}

// ---------------------------------------------------------------------
// Canvas drawing
// ---------------------------------------------------------------------
function roundRect(ctx, x, y, w, h, r, fill, stroke) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function text(ctx, str, x, y, { size = 28, weight = 600, color = C.text, align = "left", font = FONT } = {}) {
  ctx.font = `${weight} ${size}px ${font}`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(str, x, y);
}

function fitText(ctx, str, maxWidth, opts) {
  ctx.font = `${opts.weight || 600} ${opts.size || 28}px ${opts.font || FONT}`;
  if (ctx.measureText(str).width <= maxWidth) return str;
  let s = str;
  while (s.length > 1 && ctx.measureText(`${s}…`).width > maxWidth) s = s.slice(0, -1);
  return `${s}…`;
}

function drawShareCard(canvas, m, host) {
  canvas.width = CARD_W;
  canvas.height = CARD_H;
  const ctx = canvas.getContext("2d");
  const P = 64;
  const W = CARD_W - P * 2;
  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, CARD_W, CARD_H);

  // Header
  roundRect(ctx, P, 60, 56, 56, 14, C.accent);
  ctx.strokeStyle = "#FFFFFF";
  ctx.lineWidth = 5;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(P + 13, 60 + 38);
  ctx.lineTo(P + 24, 60 + 24);
  ctx.lineTo(P + 32, 60 + 32);
  ctx.lineTo(P + 44, 60 + 16);
  ctx.stroke();
  text(ctx, "Quantile", P + 76, 98, { size: 40, weight: 800 });
  text(ctx, "Market view", P + 76, 132, { size: 24, weight: 600, color: C.text2 });
  text(ctx, istDate(m.at), CARD_W - P, 92, { size: 26, weight: 700, align: "right" });
  text(ctx, `${istTime(m.at)} IST`, CARD_W - P - 132, 130, { size: 24, weight: 600, color: C.text2, align: "right" });
  const pill = m.live ? { label: "● LIVE", fill: "rgba(74,222,156,0.16)", color: C.up } : { label: "CLOSE", fill: "rgba(255,255,255,0.08)", color: C.text2 };
  roundRect(ctx, CARD_W - P - 118, 104, 118, 36, 18, pill.fill);
  text(ctx, pill.label, CARD_W - P - 59, 130, { size: 20, weight: 800, color: pill.color, align: "center" });

  // Index boxes
  let y = 176;
  const gap = 20;
  const boxW = (W - gap * 2) / 3;
  m.indices.slice(0, 3).forEach((ix, i) => {
    const x = P + i * (boxW + gap);
    const up = (ix.change ?? 0) >= 0;
    roundRect(ctx, x, y, boxW, 170, 18, C.card, C.border);
    text(ctx, ix.label, x + 24, y + 46, { size: 22, weight: 700, color: C.text2 });
    text(ctx, fmt(ix.value), x + 24, y + 104, { size: 42, weight: 700, font: NUM_FONT });
    text(ctx, `${up ? "▲" : "▼"} ${signed(ix.change)} (${signed(ix.pct)}%)`, x + 24, y + 145, { size: 22, weight: 600, color: up ? C.up : C.down, font: NUM_FONT });
  });

  // Breadth + VIX
  y += 170 + 24;
  roundRect(ctx, P, y, W, 128, 18, C.card, C.border);
  text(ctx, "Market breadth", P + 28, y + 46, { size: 24, weight: 700 });
  if (m.breadth) {
    const total = m.breadth.advancing + m.breadth.declining;
    const advPct = total ? m.breadth.advancing / total : 0.5;
    text(ctx, `${m.breadth.advancing} advancing`, P + 28, y + 96, { size: 26, weight: 700, color: C.up, font: NUM_FONT });
    const barX = P + 290;
    const barW = W - 290 - (m.vix ? 250 : 40);
    roundRect(ctx, barX, y + 80, barW * advPct - 2, 18, 9, C.up);
    roundRect(ctx, barX + barW * advPct + 2, y + 80, barW * (1 - advPct) - 2, 18, 9, C.down);
    text(ctx, `${m.breadth.declining} declining`, barX + barW, y + 64, { size: 22, weight: 700, color: C.down, align: "right", font: NUM_FONT });
  } else {
    text(ctx, "Not available yet", P + 28, y + 96, { size: 24, weight: 600, color: C.muted });
  }
  if (m.vix) {
    text(ctx, "India VIX", CARD_W - P - 28, y + 46, { size: 22, weight: 700, color: C.text2, align: "right" });
    text(ctx, fmt(m.vix.value), CARD_W - P - 28, y + 98, { size: 36, weight: 700, align: "right", font: NUM_FONT });
  }

  // Sector columns
  y += 128 + 24;
  const colW = (W - gap) / 2;
  const sectorBox = (x, title, rows, up) => {
    roundRect(ctx, x, y, colW, 280, 18, C.card, C.border);
    text(ctx, title, x + 28, y + 50, { size: 26, weight: 800, color: up ? C.up : C.down });
    rows.forEach((r, i) => {
      const ry = y + 110 + i * 60;
      text(ctx, fitText(ctx, shortSector(r.name), colW - 200, { size: 28, weight: 700 }), x + 28, ry, { size: 28, weight: 700 });
      text(ctx, `${signed(r.changePct)}%`, x + colW - 28, ry, { size: 28, weight: 700, color: r.changePct >= 0 ? C.up : C.down, align: "right", font: NUM_FONT });
    });
  };
  sectorBox(P, "▲ Top sectors", m.topSectors, true);
  sectorBox(P + colW + gap, "▼ Bottom sectors", m.bottomSectors, false);

  // Stocks in the strongest / weakest sector
  y += 280 + 24;
  const stockBox = (x, title, sub, rows, up) => {
    roundRect(ctx, x, y, colW, 386, 18, C.card, C.border);
    text(ctx, title, x + 28, y + 48, { size: 24, weight: 800, color: up ? C.up : C.down });
    // NUM_FONT: Manrope has no U+2212 minus glyph, so "(−0.47%)" rendered
    // as "( 0.47%)" in the heading font.
    text(ctx, fitText(ctx, sub, colW - 56, { size: 22, weight: 600, font: NUM_FONT }), x + 28, y + 82, { size: 22, weight: 600, color: C.text2, font: NUM_FONT });
    if (!rows.length) text(ctx, "Loading…", x + 28, y + 140, { size: 24, weight: 600, color: C.muted });
    rows.forEach((r, i) => {
      const ry = y + 146 + i * 64;
      text(ctx, fitText(ctx, r.symbol, colW - 220, { size: 27, weight: 700 }), x + 28, ry, { size: 27, weight: 700 });
      text(ctx, `${signed(r.changePct)}%`, x + colW - 28, ry, { size: 27, weight: 700, color: r.changePct >= 0 ? C.up : C.down, align: "right", font: NUM_FONT });
    });
  };
  if (m.best) stockBox(P, "Leading stocks", `in ${shortSector(m.best.name)} (${signed(m.best.changePct)}%)`, m.bestStocks, true);
  if (m.worst) stockBox(P + colW + gap, "Lagging stocks", `in ${shortSector(m.worst.name)} (${signed(m.worst.changePct)}%)`, m.worstStocks, false);

  // Footer
  text(ctx, "Market data summary, not investment advice.", P, CARD_H - 56, { size: 21, weight: 600, color: C.muted });
  if (host) text(ctx, host, CARD_W - P, CARD_H - 56, { size: 21, weight: 700, color: C.text2, align: "right" });
}

// ---------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------
const btn = (primary, disabled) => ({
  border: primary ? "none" : "1px solid #E3E6EC", cursor: disabled ? "default" : "pointer", fontFamily: "inherit", fontSize: 13.5, fontWeight: 700,
  padding: "10px 14px", borderRadius: 9, background: primary ? (disabled ? "#A9A6EF" : "#4640DE") : "#FFFFFF", color: primary ? "#FFFFFF" : "#14171F", opacity: disabled && !primary ? 0.5 : 1,
});

export default function MarketViewShare({ data, tiles, onClose }) {
  const canvasRef = useRef(null);
  const [stocks, setStocks] = useState(null);
  const [status, setStatus] = useState(null); // {tone, text}
  const [sending, setSending] = useState(false);
  const [audience, setAudience] = useState({ pro: true, premium: true, free: false });
  const [confirming, setConfirming] = useState(false);
  const url = `${window.location.origin}/markets/sectors`;
  const host = window.location.host;

  const sorted = useMemo(() => [...(tiles || [])].filter((t) => t.changePct != null).sort((a, b) => b.changePct - a.changePct), [tiles]);
  const bestSym = sorted[0]?.symbol;
  const worstSym = sorted[sorted.length - 1]?.symbol;

  useEffect(() => {
    if (!bestSym) return undefined;
    let cancelled = false;
    apiFetch(`/api/markets/sector-stocks?symbols=${encodeURIComponent([bestSym, worstSym].filter(Boolean).join(","))}`)
      .then((r) => (r.ok ? r.json() : { sectors: {} }))
      .then((d) => !cancelled && setStocks(d.sectors || {}))
      .catch(() => !cancelled && setStocks({}));
    return () => {
      cancelled = true;
    };
  }, [bestSym, worstSym]);

  const model = useMemo(() => buildMarketView(data, tiles, stocks), [data, tiles, stocks]);
  const generated = useMemo(() => buildCaption(model, url), [model, url]);
  const [message, setMessage] = useState(null); // null = follow the generated text
  const [title, setTitle] = useState(null);
  const effectiveMessage = message ?? generated;
  const effectiveTitle = title ?? `📊 Market view · ${istTime(model.at)}`;

  useEffect(() => {
    let cancelled = false;
    // Wait for web fonts so the canvas doesn't fall back mid-draw.
    (document.fonts?.ready || Promise.resolve()).then(() => {
      if (!cancelled && canvasRef.current) drawShareCard(canvasRef.current, model, host);
    });
    return () => {
      cancelled = true;
    };
  }, [model, host]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pngBlob = () => new Promise((resolve) => canvasRef.current.toBlob(resolve, "image/png"));
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");

  async function copyImage() {
    try {
      if (!navigator.clipboard?.write || typeof window.ClipboardItem === "undefined") throw new Error("unsupported");
      // Promise form: Safari requires the ClipboardItem to be created
      // synchronously inside the click, with the blob resolved later.
      await navigator.clipboard.write([new window.ClipboardItem({ "image/png": pngBlob() })]);
      setStatus({ tone: "ok", text: "Image copied — paste it into WhatsApp, Telegram or anywhere." });
    } catch {
      setStatus({ tone: "warn", text: "This browser can't copy images. Use Download PNG instead." });
    }
  }

  async function downloadImage() {
    const blob = await pngBlob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `quantile-market-view-${stamp()}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    setStatus({ tone: "ok", text: "PNG downloaded." });
  }

  async function copyText() {
    try {
      await navigator.clipboard.writeText(effectiveMessage);
      setStatus({ tone: "ok", text: "Text copied." });
    } catch {
      setStatus({ tone: "warn", text: "Couldn't copy — select the text and copy it manually." });
    }
  }

  // In-app/push: the "Sector view: <url>" line becomes the campaign CTA
  // button convention ([Label](url)) the bell, chat and push all render.
  const notificationBody = () => {
    const lines = effectiveMessage.split("\n").filter((l) => !l.startsWith("Sector view:"));
    return `${lines.join("\n")}\n[Open Sector view](${url})`;
  };

  async function send(test, force = false) {
    const chosen = Object.keys(audience).filter((k) => audience[k]);
    if (!test && !chosen.length) {
      setStatus({ tone: "warn", text: "Choose at least one audience." });
      return;
    }
    setSending(true);
    setStatus(null);
    try {
      const res = await apiFetch("/api/admin/market-view/send", {
        method: "POST",
        body: JSON.stringify({ title: effectiveTitle, body: notificationBody(), audience: chosen, test, force }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.status === 409 && d.duplicate) {
        setStatus({ tone: "warn", text: `${d.error} Press "Send anyway" to send it again.`, duplicate: true });
      } else if (!res.ok) {
        setStatus({ tone: "warn", text: d.error || "Send failed." });
      } else if (test) {
        setStatus({ tone: "ok", text: `Test push sent to ${d.pushSent} of your device(s).` });
      } else {
        setStatus({ tone: "ok", text: `Sent to ${d.recipientCount} subscriber(s) — in-app${d.channels?.includes("push") ? ` + push (${d.pushSent} devices)` : " only (push not configured)"}.` });
      }
    } catch {
      setStatus({ tone: "warn", text: "Send failed — check your connection." });
    } finally {
      setSending(false);
      setConfirming(false);
    }
  }

  const label = { fontSize: 12, fontWeight: 700, color: "#5B6270", textTransform: "uppercase", letterSpacing: "0.04em", display: "block", marginBottom: 6 };

  return (
    <div role="dialog" aria-modal="true" aria-label="Share market view" onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(10,12,18,0.72)", zIndex: 2000, display: "flex", alignItems: "flex-start", justifyContent: "center", overflowY: "auto", padding: "clamp(12px, 4vw, 40px) 12px" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#FFFFFF", color: "#14171F", borderRadius: 18, width: "min(980px, 100%)", padding: "clamp(16px, 3vw, 26px)", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Share market view</h2>
            <p style={{ fontSize: 13, color: "#5B6270", margin: "4px 0 0" }}>Copy the image to paste anywhere. Send pushes the text to subscribers — the image is never uploaded.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", fontSize: 26, lineHeight: 1, cursor: "pointer", color: "#8A90A0" }}>×</button>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-start" }}>
          <div style={{ flex: "0 1 340px", minWidth: 240, display: "flex", flexDirection: "column", gap: 10 }}>
            <canvas ref={canvasRef} width={CARD_W} height={CARD_H} style={{ width: "100%", height: "auto", borderRadius: 12, border: "1px solid #E3E6EC", display: "block" }} aria-label="Market view share card preview" />
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" onClick={copyImage} style={{ ...btn(true, false), flex: 1 }}>Copy image</button>
              <button type="button" onClick={downloadImage} style={{ ...btn(false, false), flex: 1 }}>Download PNG</button>
            </div>
          </div>

          <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <span style={label}>Message (copied as text and sent in-app/push)</span>
              <textarea
                value={effectiveMessage}
                onChange={(e) => setMessage(e.target.value)}
                rows={9}
                style={{ width: "100%", boxSizing: "border-box", fontFamily: "inherit", fontSize: 13.5, lineHeight: 1.5, padding: 12, borderRadius: 10, border: "1px solid #E3E6EC", resize: "vertical" }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                <button type="button" onClick={copyText} style={btn(false, false)}>Copy text</button>
                {message != null && (
                  <button type="button" onClick={() => setMessage(null)} style={btn(false, false)}>Reset to latest data</button>
                )}
              </div>
            </div>

            <div style={{ borderTop: "1px solid #F0F1F4", paddingTop: 14 }}>
              <span style={label}>Send to subscribers</span>
              <input
                value={effectiveTitle}
                onChange={(e) => setTitle(e.target.value)}
                aria-label="Notification title"
                style={{ width: "100%", boxSizing: "border-box", fontFamily: "inherit", fontSize: 14, fontWeight: 700, padding: "10px 12px", borderRadius: 10, border: "1px solid #E3E6EC", marginBottom: 10 }}
              />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 12 }}>
                {AUDIENCES.map((a) => (
                  <label key={a.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13.5, fontWeight: 600, cursor: "pointer" }}>
                    <input type="checkbox" checked={audience[a.key]} onChange={(e) => setAudience((s) => ({ ...s, [a.key]: e.target.checked }))} />
                    {a.label}
                  </label>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="button" disabled={sending} onClick={() => send(true)} style={btn(false, sending)}>Send test to me</button>
                {!confirming ? (
                  <button type="button" disabled={sending} onClick={() => setConfirming(true)} style={btn(true, sending)}>Send to subscribers</button>
                ) : (
                  <>
                    <button type="button" disabled={sending} onClick={() => send(false)} style={{ ...btn(true, sending), background: "#17A673" }}>{sending ? "Sending…" : "Confirm send"}</button>
                    <button type="button" disabled={sending} onClick={() => setConfirming(false)} style={btn(false, sending)}>Cancel</button>
                  </>
                )}
                {status?.duplicate && (
                  <button type="button" disabled={sending} onClick={() => send(false, true)} style={btn(false, sending)}>Send anyway</button>
                )}
              </div>
              <p style={{ fontSize: 12, color: "#8A90A0", margin: "8px 0 0" }}>Goes to the bell, the dashboard chat and push notifications, with an "Open Sector view" button.</p>
            </div>

            {status && (
              <div role="status" style={{ fontSize: 13, fontWeight: 600, padding: "10px 12px", borderRadius: 10, background: status.tone === "ok" ? "#E6F7F1" : "#FBF2E1", color: status.tone === "ok" ? "#127A55" : "#8A6516" }}>{status.text}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
