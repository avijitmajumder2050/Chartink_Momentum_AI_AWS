import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../../api/client";
import { useChartPreview } from "../../chart/ChartPreviewContext";

// Ported from templates/admin_scanner_campaign.html (996 lines, the
// biggest/most logic-heavy page in the app) + its inline script. New
// GET /api/admin/scanner-campaign/bootstrap (app.py) replaces the
// entries/notifications/templates/push-config bootstrap that used to be
// inline in admin_scanner_campaign_page() — scanner results themselves
// reuse the same GET /api/scanners + /api/scanners/<id>/cached the
// Scanner page already calls. The default-template auto-seed that used
// to be a side effect of the GET is now an explicit action (see
// seedDefaultTemplate below), called once if bootstrap comes back with
// no templates.

const SCANNER_TYPE = { dhan_ema_breakout: "momentum", stoch: "swing" };
const MILESTONE_LABELS = { entry_triggered: "Entry", profit_2pct: "+2%", rr_1_1: "1:1", rr_1_2: "1:2", sl_hit: "SL Hit" };
const MILESTONE_ORDER = ["entry_triggered", "profit_2pct", "rr_1_1", "rr_1_2", "sl_hit"];
const TYPE_LABEL = { momentum: "Momentum", swing: "Swing" };

function postJson(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) }).then((res) =>
    res.json().then((data) => ({ ok: res.ok, data }))
  );
}

function escapeHtml(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function linkify(escapedText) {
  return escapedText.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, label, url) => `<a href="${url}" target="_blank" rel="noopener" class="notif-card-link">${label}</a>`);
}

function renderLine(tpl, entry) {
  return tpl
    .replace(/\{\{symbol\}\}/g, entry.symbol).replace(/\{\{entry\}\}/g, entry.entry)
    .replace(/\{\{sl\}\}/g, entry.sl).replace(/\{\{target\}\}/g, entry.target).replace(/\{\{note\}\}/g, entry.note)
    .replace(/\{\{chart_url\}\}/g, entry.chart_url)
    .replace(/\{\{current\}\}/g, entry.current).replace(/\{\{profit\}\}/g, entry.profit).replace(/\{\{milestones\}\}/g, entry.milestones);
}

function todayDDMMYYYY() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()}`;
}

function milestonesSummaryText(reached) {
  if (!reached || !reached.length) return "No milestones yet";
  return reached.map((m) => MILESTONE_LABELS[m] || m).join(" · ");
}

const inputStyle = { border: "1.5px solid #E3E6EC", borderRadius: 7, padding: "7px 9px", fontSize: 12.5, fontFamily: "inherit" };

export default function AdminScannerCampaign() {
  const { openPreview } = useChartPreview();

  const [message, setMessageState] = useState(null);
  function showMessage(text, isError) {
    setMessageState({ text, isError });
  }

  // ---- Scanners ----
  const [scanners, setScanners] = useState([]);
  const [scannerResults, setScannerResults] = useState({}); // sid -> {columns, rows, generatedAt}
  const [runningScanner, setRunningScanner] = useState(null);

  useEffect(() => {
    apiFetch("/api/scanners").then((res) => res.json()).then((list) => {
      setScanners(list);
      list.forEach((s) => {
        apiFetch(`/api/scanners/${encodeURIComponent(s.id)}/cached`).then((res) => res.json()).then((data) => {
          if (data.cached) {
            setScannerResults((prev) => ({ ...prev, [s.id]: { columns: data.columns, rows: data.rows, generatedAt: data.generated_at } }));
          }
        });
      });
    });
  }, []);

  function runScanner(sid) {
    setRunningScanner(sid);
    apiFetch(`/api/scanners/${encodeURIComponent(sid)}/run`)
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        setRunningScanner(null);
        if (!result.ok || result.data.error) {
          showMessage(result.data.error || "Couldn't run scanner.", true);
          return;
        }
        setScannerResults((prev) => ({ ...prev, [sid]: { columns: result.data.columns, rows: result.data.rows, generatedAt: result.data.generated_at } }));
      })
      .catch(() => setRunningScanner(null));
  }

  // ---- AI Top 5 Picks ----
  const [aiScreening, setAiScreening] = useState(false);
  const [aiScreenResult, setAiScreenResult] = useState(null); // {picks, screened, skipped}
  const [aiAddedSymbols, setAiAddedSymbols] = useState(() => new Set());

  function runAiScreen() {
    setAiScreening(true);
    setAiScreenResult(null);
    apiFetch("/api/admin/campaign/ai-screen")
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        setAiScreening(false);
        if (!result.ok) {
          showMessage(result.data.error || "AI screening failed.", true);
          return;
        }
        setAiScreenResult(result.data);
      })
      .catch(() => {
        setAiScreening(false);
        showMessage("AI screening failed.", true);
      });
  }

  // ---- Campaign entries ----
  const [entries, setEntries] = useState([]);
  const [addFormOpen, setAddFormOpen] = useState(false);
  const [addForm, setAddForm] = useState({ symbol: "", type: "", entryPrice: "", slPrice: "", targetPrice: "", note: "" });

  const loadBootstrap = useCallback(() => {
    return apiFetch("/api/admin/scanner-campaign/bootstrap")
      .then((res) => res.json())
      .then((data) => {
        setEntries(data.entries);
        setNotifications(data.notifications);
        setTemplates(data.templates);
        setPushConfigured(data.pushConfigured);
        setPushTokenCount(data.pushTokenCount);
        if (!data.templates.length) {
          postJson("/api/admin/scanner-campaign/seed-default-template", {}).then((r) => {
            if (r.ok) setTemplates([r.data.template]);
          });
        }
      })
      .catch(() => showMessage("Couldn't load the campaign console. Refresh to retry.", true));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setters below are stable
  }, []);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  function addEntry(payload) {
    return postJson("/api/admin/campaign-entries", payload).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't add entry.", true);
        return null;
      }
      showMessage(`${result.data.entry.symbol} added to campaign entries.`, false);
      setEntries((prev) => [result.data.entry, ...prev]);
      loadTracker();
      return result.data.entry;
    });
  }

  function submitAddForm(e) {
    e.preventDefault();
    addEntry({
      symbol: addForm.symbol, entryPrice: addForm.entryPrice || undefined, slPrice: addForm.slPrice || undefined,
      targetPrice: addForm.targetPrice || undefined, note: addForm.note, source: "manual", type: addForm.type,
    }).then((entry) => {
      if (entry) {
        setAddForm({ symbol: "", type: "", entryPrice: "", slPrice: "", targetPrice: "", note: "" });
        setAddFormOpen(false);
      }
    });
  }

  function addFromScanner(sid, row, symbolKey, priceKey, highKey, lowKey) {
    const high = highKey ? parseFloat(row[highKey]) : NaN;
    const low = lowKey ? parseFloat(row[lowKey]) : NaN;
    const payload = { symbol: row[symbolKey], source: "scanner", type: SCANNER_TYPE[sid] || "" };
    if (!isNaN(high) && !isNaN(low)) {
      payload.entryPrice = high;
      payload.slPrice = low;
      payload.targetPrice = Math.round(high * 1.1 * 100) / 100;
    } else if (priceKey) {
      payload.entryPrice = row[priceKey];
    }
    addEntry(payload);
  }

  function addFromAiPick(pick) {
    addEntry({
      symbol: pick.symbol, source: "scanner", type: "momentum",
      entryPrice: pick.high, slPrice: pick.low, targetPrice: Math.round(pick.high * 1.1 * 100) / 100,
    }).then((entry) => {
      if (entry) setAiAddedSymbols((prev) => new Set(prev).add(pick.symbol));
    });
  }

  function updateEntryField(id, field, value) {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, [fieldToEntryKey(field)]: value } : e)));
    postJson(`/api/admin/campaign-entries/${id}/update`, { [field]: value }).then((result) => {
      if (!result.ok) showMessage(result.data.error || "Couldn't save.", true);
      else showMessage("Saved.", false);
    });
  }

  function fieldToEntryKey(field) {
    return { entryPrice: "entry_price", slPrice: "sl_price", targetPrice: "target_price", note: "note", type: "type" }[field] || field;
  }

  function deleteEntry(entry) {
    if (!window.confirm(`Remove ${entry.symbol} from campaign entries?`)) return;
    postJson(`/api/admin/campaign-entries/${entry.id}/delete`, {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete.", true);
        return;
      }
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
      loadTracker();
    });
  }

  // ---- Alert tracker ----
  const [tracker, setTracker] = useState([]);
  // Shared between the Campaign entries table and the Alert tracker card
  // below — both list the same underlying entries (by id), just with
  // different columns, and either one's checkboxes feed the Campaign
  // text builder further down the page.
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const trackerByIdRef = useRef({});

  const loadTracker = useCallback(() => {
    return apiFetch("/api/admin/campaign/tracker").then((res) => res.json()).then((data) => {
      const list = data.entries || [];
      trackerByIdRef.current = Object.fromEntries(list.map((e) => [e.id, e]));
      setTracker(list);
      setSelectedIds((prev) => new Set([...prev].filter((id) => list.some((e) => e.id === id))));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadTracker();
    const t = setInterval(loadTracker, 60000);
    return () => clearInterval(t);
  }, [loadTracker]);

  function toggleSelected(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleTrackerSelectAll(checked) {
    setSelectedIds(checked ? new Set(tracker.map((e) => e.id)) : new Set());
  }

  function toggleEntriesSelectAll(checked) {
    setSelectedIds(checked ? new Set(entries.map((e) => e.id)) : new Set());
  }

  function deleteSelectedTracked() {
    const rows = tracker.filter((e) => selectedIds.has(e.id));
    if (!rows.length) return;
    if (!window.confirm(`Stop tracking ${rows.length} stock(s) (${rows.map((r) => r.symbol).join(", ")})? This removes them from campaign entries too.`)) return;

    Promise.all(rows.map((r) => postJson(`/api/admin/campaign-entries/${r.id}/delete`, {}))).then((results) => {
      const failed = results.filter((r) => !r.ok).length;
      const ids = new Set(rows.map((r) => r.id));
      setEntries((prev) => prev.filter((e) => !ids.has(e.id)));
      setSelectedIds(new Set());
      loadTracker();
      showMessage(failed ? `${failed} couldn't be removed.` : `Stopped tracking ${rows.length} stock(s).`, !!failed);
    });
  }

  // ---- Notifications history ----
  const [notifications, setNotifications] = useState([]);
  const [notificationsSelected, setNotificationsSelected] = useState(() => new Set());

  function toggleNotificationSelected(id) {
    setNotificationsSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function deleteNotification(id) {
    if (!window.confirm("Delete this campaign? It will also disappear from subscribers' in-app notification inbox.")) return;
    postJson(`/api/admin/campaign-notifications/${id}/delete`, {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete.", true);
        return;
      }
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    });
  }

  function deleteSelectedNotifications() {
    const ids = [...notificationsSelected];
    if (!ids.length) return;
    if (!window.confirm(`Delete ${ids.length} campaign(s)? They will also disappear from subscribers' in-app notification inbox.`)) return;
    postJson("/api/admin/campaign-notifications/delete-batch", { ids }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete.", true);
        return;
      }
      setNotifications((prev) => prev.filter((n) => !notificationsSelected.has(n.id)));
      setNotificationsSelected(new Set());
      showMessage(`Deleted ${result.data.deleted} campaign(s).`, false);
    });
  }

  // ---- Templates + compose ----
  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [tplTitle, setTplTitle] = useState("");
  const [tplHeader, setTplHeader] = useState("");
  const [tplLine, setTplLine] = useState("{{symbol}} — Entry {{entry}}, SL {{sl}}, Target {{target}}");
  const [tplFooter, setTplFooter] = useState("");
  const [titleSource, setTitleSource] = useState("auto");
  const [headerSource, setHeaderSource] = useState("auto");
  const [titleVariants, setTitleVariants] = useState({ auto: "", ai: "" });
  const [headerVariants, setHeaderVariants] = useState({ auto: "", ai: "" });
  const [aiCopyAvailable, setAiCopyAvailable] = useState(false);
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [templateNameInput, setTemplateNameInput] = useState("");
  const [audience, setAudience] = useState({ free: false, pro: true, premium: true });
  const [channels, setChannels] = useState({ inApp: true, push: false });
  const [pushConfigured, setPushConfigured] = useState(false);
  const [pushTokenCount, setPushTokenCount] = useState(0);
  const [sending, setSending] = useState(false);

  // Mirrors the original's server-rendered initial state: tplLine/
  // tplFooter start pre-filled from templates[0] (and it's pre-selected
  // in the dropdown) — tplTitle/tplHeader deliberately do NOT, they stay
  // whatever autoFillTemplateDefaults() already set.
  const templatePrefillDone = useRef(false);
  useEffect(() => {
    if (templates.length && !templatePrefillDone.current) {
      templatePrefillDone.current = true;
      setSelectedTemplateId(templates[0].id);
      setTplLine(templates[0].entry_line_template || "");
      setTplFooter(templates[0].footer || "");
    }
  }, [templates]);

  // selectedEntries(): reads checked rows by id — checkable from either
  // the Campaign entries table or the Alert tracker card, both keyed to
  // the same entry ids — and drives what goes into a campaign message.
  const selectedEntries = useMemo(() => {
    return tracker
      .filter((t) => selectedIds.has(t.id))
      .map((t) => {
        const entryRow = entries.find((e) => e.id === t.id);
        const symbol = t.symbol;
        return {
          symbol,
          type: entryRow?.type || "",
          entry: t.entryPrice != null ? t.entryPrice.toFixed(2) : "—",
          sl: t.slPrice != null ? t.slPrice.toFixed(2) : "—",
          target: t.targetPrice != null ? t.targetPrice.toFixed(2) : "—",
          note: entryRow?.note || "",
          chart_url: `${window.location.origin}/markets/chart?symbol=${encodeURIComponent(symbol)}`,
          current: t.currentPrice != null ? t.currentPrice.toFixed(2) : "—",
          profit: t.profitPct != null ? (t.profitPct >= 0 ? "+" : "") + t.profitPct.toFixed(2) + "%" : "—",
          milestones: milestonesSummaryText(t.milestonesReached),
        };
      });
  }, [tracker, selectedIds, entries]);

  const autoFillTemplateDefaults = useCallback(() => {
    const types = selectedEntries.map((e) => e.type).filter(Boolean);
    const distinct = [...new Set(types)];
    const date = todayDDMMYYYY();
    const label = distinct.length === 1 ? TYPE_LABEL[distinct[0]] : null;
    const autoTitle = `${label || "Watchlist"}${label ? " watchlist " : " "}${date}`;
    const autoHeader = `Today's ${label ? label.toLowerCase() + " " : ""}watchlist — handpicked from live scanner results:`;
    setTitleVariants((prev) => ({ ...prev, auto: autoTitle }));
    setHeaderVariants((prev) => ({ ...prev, auto: autoHeader }));
    setTitleSource((src) => {
      if (src === "auto") setTplTitle(autoTitle);
      return src;
    });
    setHeaderSource((src) => {
      if (src === "auto") setTplHeader(autoHeader);
      return src;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEntries]);

  useEffect(() => {
    autoFillTemplateDefaults();
  }, [autoFillTemplateDefaults]);

  function composeBody() {
    if (!selectedEntries.length) return null;
    const lines = selectedEntries.map((e) => renderLine(tplLine, e));
    const parts = [tplHeader.trim(), lines.join("\n"), tplFooter.trim()].filter(Boolean);
    return parts.join("\n\n");
  }

  const previewHtml = useMemo(() => {
    const body = composeBody();
    if (!body) return null;
    const title = tplTitle.trim() || "Quantile";
    return { title, bodyHtml: linkify(escapeHtml(body)) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEntries, tplHeader, tplLine, tplFooter, tplTitle]);

  function onTemplateSelect(id) {
    setSelectedTemplateId(id);
    if (!id) return;
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setTplTitle(t.title || "");
    setTplHeader(t.header || "");
    setTplLine(t.entry_line_template || "");
    setTplFooter(t.footer || "");
  }

  function deleteTemplate() {
    if (!selectedTemplateId) return;
    const t = templates.find((x) => x.id === selectedTemplateId);
    if (!window.confirm(`Delete the template "${t?.name}"? This cannot be undone.`)) return;
    postJson(`/api/admin/campaign-templates/${selectedTemplateId}/delete`, {}).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't delete template.", true);
        return;
      }
      setTemplates((prev) => prev.filter((x) => x.id !== selectedTemplateId));
      setSelectedTemplateId("");
    });
  }

  function saveTemplate() {
    const name = templateNameInput.trim();
    if (!name) {
      showMessage("Enter a name to save this as a template.", true);
      return;
    }
    postJson("/api/admin/campaign-templates", { name, title: tplTitle, header: tplHeader, entryLineTemplate: tplLine, footer: tplFooter }).then((result) => {
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't save template.", true);
        return;
      }
      showMessage(`Template "${name}" saved.`, false);
      setTemplates((prev) => [...prev, result.data.template]);
      setTemplateNameInput("");
    });
  }

  function generateWithAi() {
    setAiGenerating(true);
    postJson("/api/admin/campaign/ai-generate", { instruction: aiInstruction.trim(), entries: selectedEntries }).then((result) => {
      setAiGenerating(false);
      if (!result.ok) {
        showMessage(result.data.error || "AI generation failed.", true);
        return;
      }
      setTitleVariants((prev) => ({ ...prev, ai: result.data.title }));
      setHeaderVariants((prev) => ({ ...prev, ai: result.data.header }));
      setAiCopyAvailable(true);
      setTitleSource("ai");
      setHeaderSource("ai");
      setTplTitle(result.data.title);
      setTplHeader(result.data.header);
      setTplLine(result.data.entryLineTemplate);
      showMessage('AI-generated copy filled in — switch the dropdown next to Title/Header back to "Auto" anytime to undo.', false);
    });
  }

  function onTitleSourceChange(src) {
    setTitleSource(src);
    setTplTitle(titleVariants[src] || "");
  }
  function onHeaderSourceChange(src) {
    setHeaderSource(src);
    setTplHeader(headerVariants[src] || "");
  }

  function sendCampaign() {
    const title = tplTitle.trim();
    const body = composeBody();
    if (!title) {
      showMessage("Enter a notification title.", true);
      return;
    }
    if (!body) {
      showMessage("Select at least one entry.", true);
      return;
    }
    const channelList = [];
    if (channels.inApp) channelList.push("in_app");
    if (channels.push) channelList.push("push");
    if (!channelList.length) {
      showMessage("Choose at least one channel.", true);
      return;
    }
    const audienceList = Object.entries(audience).filter(([, v]) => v).map(([k]) => k);
    if (!audienceList.length) {
      showMessage("Choose at least one audience (Free/Pro/Premium).", true);
      return;
    }
    if (!window.confirm(`Send this campaign to ${audienceList.join(", ")} users now?`)) return;

    setSending(true);
    postJson("/api/admin/campaign/send", { title, body, entrySymbols: selectedEntries.map((e) => e.symbol), channels: channelList, audience: audienceList }).then((result) => {
      setSending(false);
      if (!result.ok) {
        showMessage(result.data.error || "Couldn't send campaign.", true);
        return;
      }
      showMessage(`Sent to ${result.data.recipientCount} users${channelList.includes("push") ? ` (${result.data.pushSent} push deliveries)` : ""}.`, false);
      loadBootstrap();
    });
  }

  function onSymbolClick(e, symbol) {
    e.preventDefault();
    openPreview(symbol);
  }

  return (
    <div style={{ padding: "30px clamp(16px, 4vw, 36px) 80px", maxWidth: 1200 }}>
      <div style={{ marginBottom: 22 }}>
        <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Admin</span>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginTop: 6 }}>Scanner campaign</h1>
        <p style={{ fontSize: 13, color: "#5B6270", marginTop: 6 }}>Run scanners, curate trade ideas with entry/SL/target prices, and notify subscribers.</p>
      </div>

      {message && (
        <div style={{ fontSize: 13, fontWeight: 600, padding: "11px 14px", borderRadius: 10, marginBottom: 18, background: message.isError ? "#FDEDEC" : "#EAF7F1", color: message.isError ? "#C0392B" : "#17A673" }}>
          {message.text}
        </div>
      )}

      {/* SCANNER RESULTS */}
      {scanners.map((s) => {
        const res = scannerResults[s.id];
        const columns = (res?.columns || []).filter((c) => c.key !== "Security ID" && c.key !== "Scan Time").slice(0, 6);
        const symbolCol = res?.columns?.find((c) => c.type === "symbol");
        const priceCol = res?.columns?.find((c) => c.key === "Price" || c.key === "Close");
        const highCol = res?.columns?.find((c) => c.key === "High");
        const lowCol = res?.columns?.find((c) => c.key === "Low");
        return (
          <div key={s.id} style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <span style={{ fontSize: 14.5, fontWeight: 700 }}>{s.name}</span>
                <span style={{ fontSize: 12, color: "#8A90A0", marginLeft: 8 }}>{res?.generatedAt ? `as of ${res.generatedAt}` : "not run yet"}</span>
              </div>
              <button type="button" disabled={runningScanner === s.id} onClick={() => runScanner(s.id)} style={{ border: "1.5px solid #E3E6EC", background: "#FFFFFF", borderRadius: 9, padding: "8px 16px", fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>
                {runningScanner === s.id ? "Running…" : "Run scanner"}
              </button>
            </div>
            {!res || !res.rows?.length ? (
              <p style={{ fontSize: 12.5, color: "#8A90A0", margin: "6px 0 0" }}>No cached result — click "Run scanner".</p>
            ) : (
              <div className="table-wrap">
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {columns.map((c) => <th key={c.key} style={{ textAlign: "left", fontSize: 10.5, color: "#8A90A0", textTransform: "uppercase", padding: "6px 8px" }}>{c.label}</th>)}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {res.rows.map((row, i) => (
                    <tr key={i}>
                      {columns.map((c) => (
                        <td key={c.key} style={{ padding: "6px 8px", fontSize: 12.5, borderTop: "1px solid #F0F1F4" }}>
                          {c.type === "symbol" ? (
                            <a className="symbol-link" href={`/markets/chart?symbol=${encodeURIComponent(row[c.key])}`} target="_blank" rel="noopener noreferrer" onClick={(e) => onSymbolClick(e, row[c.key])}>
                              {row[c.key]}
                            </a>
                          ) : (
                            row[c.key] ?? "—"
                          )}
                        </td>
                      ))}
                      <td style={{ padding: "6px 8px", fontSize: 12.5, borderTop: "1px solid #F0F1F4" }}>
                        <button type="button" onClick={() => addFromScanner(s.id, row, symbolCol?.key, priceCol?.key, highCol?.key, lowCol?.key)}>+ Add</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>
        );
      })}

      {/* AI TOP 5 PICKS */}
      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>🤖 AI Top 5 Picks</span>
          <button type="button" disabled={aiScreening} onClick={runAiScreen} style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 9, padding: "8px 16px", fontSize: 12.5, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>
            {aiScreening ? "Screening… (can take up to a minute)" : "🤖 Screen Top 5"}
          </button>
        </div>
        <p style={{ fontSize: 12, color: "#8A90A0", margin: "4px 0 0" }}>
          Screens today's EMA 10/20 Breakout matches for a consolidation-breakout-on-volume setup with a bullish EMA20&gt;50&gt;100&gt;200 stack, filters out choppy price action, and ranks the best fits — run that scanner first.
        </p>
        {aiScreenResult && (
          <div>
            {!aiScreenResult.picks.length ? (
              <p style={{ fontSize: 12.5, color: "#8A90A0", marginTop: 12 }}>None of today's matches cleanly fit the setup.</p>
            ) : (
              <>
                <div style={{ fontSize: 11, color: "#8A90A0", margin: "10px 0 8px" }}>
                  Screened {aiScreenResult.screened} stock(s){aiScreenResult.skipped ? `, skipped ${aiScreenResult.skipped} with too little price history` : ""}.
                </div>
                {aiScreenResult.picks.map((p) => (
                  <div key={p.symbol} style={{ border: "1px solid #F0F1F4", borderRadius: 12, padding: 14, marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>
                        #{p.rank} <a className="symbol-link" href={`/markets/chart?symbol=${encodeURIComponent(p.symbol)}`} target="_blank" rel="noopener noreferrer" onClick={(e) => onSymbolClick(e, p.symbol)}>{p.symbol}</a>
                      </span>
                      <p style={{ fontSize: 12, color: "#5B6270", margin: "4px 0 0" }}>{p.reason}</p>
                    </div>
                    {aiAddedSymbols.has(p.symbol) ? (
                      <button type="button" disabled style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", opacity: 0.6, cursor: "default" }}>✓ Added</button>
                    ) : (
                      <button type="button" onClick={() => addFromAiPick(p)} style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>+ Add</button>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* CAMPAIGN ENTRIES */}
      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>Campaign entries</span>
          <button type="button" onClick={() => setAddFormOpen((v) => !v)} style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 9, padding: "8px 16px", fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>+ Add entry</button>
        </div>

        {addFormOpen && (
          <form onSubmit={submitAddForm} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, alignItems: "end", marginBottom: 16, padding: 14, background: "#FAF9F6", borderRadius: 10 }}>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Symbol</span>
              <input type="text" required value={addForm.symbol} onChange={(e) => setAddForm((f) => ({ ...f, symbol: e.target.value.toUpperCase() }))} style={{ ...inputStyle, width: "100%" }} />
            </label>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Type</span>
              <select required value={addForm.type} onChange={(e) => setAddForm((f) => ({ ...f, type: e.target.value }))} style={{ ...inputStyle, width: "100%" }}>
                <option value="" disabled>Select type</option>
                <option value="momentum">Momentum</option>
                <option value="swing">Swing</option>
              </select>
            </label>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Entry</span>
              <input type="number" step="0.01" value={addForm.entryPrice} onChange={(e) => setAddForm((f) => ({ ...f, entryPrice: e.target.value }))} style={{ ...inputStyle, width: "100%" }} />
            </label>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Stop loss</span>
              <input type="number" step="0.01" value={addForm.slPrice} onChange={(e) => setAddForm((f) => ({ ...f, slPrice: e.target.value }))} style={{ ...inputStyle, width: "100%" }} />
            </label>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Target</span>
              <input type="number" step="0.01" value={addForm.targetPrice} onChange={(e) => setAddForm((f) => ({ ...f, targetPrice: e.target.value }))} style={{ ...inputStyle, width: "100%" }} />
            </label>
            <label><span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Note</span>
              <input type="text" value={addForm.note} onChange={(e) => setAddForm((f) => ({ ...f, note: e.target.value }))} style={{ ...inputStyle, width: "100%" }} />
            </label>
            <button type="submit" style={{ gridColumn: "span 6", background: "#14171F", color: "white", border: "none", fontSize: 12.5, fontWeight: 700, padding: "9px 0", borderRadius: 8, cursor: "pointer" }}>Add</button>
          </form>
        )}

        <p style={{ fontSize: 11.5, color: "#8A90A0", margin: "0 0 10px" }}>Check the stocks you want in the campaign message — feeds the Campaign text builder below, same selection as the Alert tracker card.</p>
        <div className="table-wrap">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
              <th style={{ padding: "8px 10px", width: 28 }}>
                <input type="checkbox" checked={entries.length > 0 && entries.every((e) => selectedIds.has(e.id))} onChange={(ev) => toggleEntriesSelectAll(ev.target.checked)} />
              </th>
              {["Symbol", "Type", "Entry", "SL", "Target", "Note", "Source", ""].map((h) => (
                <th key={h} style={{ padding: "8px 10px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!entries.length ? (
              <tr><td colSpan={9} style={{ padding: 20, textAlign: "center", fontSize: 13, color: "#8A90A0" }}>No entries yet — add one manually or from a scanner result above.</td></tr>
            ) : (
              entries.map((e) => (
                <tr key={e.id} style={{ borderBottom: "1px solid #F0F1F4" }}>
                  <td style={{ padding: "8px 10px" }}>
                    <input type="checkbox" checked={selectedIds.has(e.id)} onChange={() => toggleSelected(e.id)} />
                  </td>
                  <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 700 }}>
                    <a className="symbol-link" href={`/markets/chart?symbol=${encodeURIComponent(e.symbol)}`} target="_blank" rel="noopener noreferrer" onClick={(ev) => onSymbolClick(ev, e.symbol)}>{e.symbol}</a>
                  </td>
                  <td style={{ padding: "8px 10px" }}>
                    <select defaultValue={e.type || ""} onChange={(ev) => updateEntryField(e.id, "type", ev.target.value)} style={{ ...inputStyle, width: 100 }}>
                      <option value="">—</option>
                      <option value="momentum">Momentum</option>
                      <option value="swing">Swing</option>
                    </select>
                  </td>
                  <td style={{ padding: "8px 10px" }}><input type="number" step="0.01" defaultValue={e.entry_price ?? ""} onBlur={(ev) => updateEntryField(e.id, "entryPrice", ev.target.value)} style={{ ...inputStyle, width: 80 }} /></td>
                  <td style={{ padding: "8px 10px" }}><input type="number" step="0.01" defaultValue={e.sl_price ?? ""} onBlur={(ev) => updateEntryField(e.id, "slPrice", ev.target.value)} style={{ ...inputStyle, width: 80 }} /></td>
                  <td style={{ padding: "8px 10px" }}><input type="number" step="0.01" defaultValue={e.target_price ?? ""} onBlur={(ev) => updateEntryField(e.id, "targetPrice", ev.target.value)} style={{ ...inputStyle, width: 80 }} /></td>
                  <td style={{ padding: "8px 10px" }}><input type="text" defaultValue={e.note || ""} onBlur={(ev) => updateEntryField(e.id, "note", ev.target.value)} style={{ ...inputStyle, width: 140 }} /></td>
                  <td style={{ padding: "8px 10px", fontSize: 12, color: "#8A90A0" }}>{e.source}</td>
                  <td style={{ padding: "8px 10px" }}>
                    <button type="button" onClick={() => deleteEntry(e)} style={{ background: "#FCEBEA", color: "#E0473F", border: "none", fontSize: 11.5, fontWeight: 700, padding: "4px 10px", borderRadius: 6, cursor: "pointer" }}>Delete</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>

      {/* ALERT TRACKER */}
      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>🎯 Alert tracker</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button type="button" disabled={!selectedIds.size} onClick={deleteSelectedTracked} style={{ background: "#FCEBEA", color: "#E0473F", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", opacity: selectedIds.size ? 1 : 0.5 }}>Delete selected</button>
            <button type="button" onClick={loadTracker} style={{ border: "1.5px solid #E3E6EC", background: "#FFFFFF", borderRadius: 9, padding: "8px 16px", fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>Refresh</button>
          </div>
        </div>
        <p style={{ fontSize: 12, color: "#8A90A0", margin: "4px 0 14px" }}>Live milestone status for every active entry — the bot auto-notifies Pro/Premium subscribers the moment each milestone is first reached, then never repeats it. Checking a box here (or in Campaign entries above) selects it for the Campaign text builder below.</p>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: "#5B6270", marginBottom: 10 }}>
          <input type="checkbox" checked={tracker.length > 0 && selectedIds.size === tracker.length} onChange={(e) => toggleTrackerSelectAll(e.target.checked)} /> Select all
        </label>
        {!tracker.length ? (
          <p style={{ fontSize: 12.5, color: "#8A90A0" }}>No active entries to track — add one above.</p>
        ) : (
          tracker.map((t) => {
            const reached = t.milestonesReached || [];
            const profitClass = t.profitPct >= 0 ? "#17A673" : "#E0473F";
            return (
              <div key={t.id} style={{ border: "1px solid #F0F1F4", borderRadius: 12, padding: 14, marginBottom: 10, display: "flex", gap: 12, alignItems: "flex-start" }}>
                <input type="checkbox" style={{ marginTop: 3 }} checked={selectedIds.has(t.id)} onChange={() => toggleSelected(t.id)} />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
                    <div>
                      <a className="symbol-link" href={`/markets/chart?symbol=${encodeURIComponent(t.symbol)}`} target="_blank" rel="noopener noreferrer" style={{ fontSize: 14, fontWeight: 700 }} onClick={(e) => onSymbolClick(e, t.symbol)}>{t.symbol}</a>
                      <span style={{ fontSize: 12, color: "#8A90A0", marginLeft: 10 }}>
                        Entry {t.entryPrice != null ? t.entryPrice.toFixed(2) : "—"}{t.slPrice != null ? ` · SL ${t.slPrice.toFixed(2)}` : ""}{t.targetPrice != null ? ` · Target ${t.targetPrice.toFixed(2)}` : ""}
                      </span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{t.currentPrice != null ? t.currentPrice.toFixed(2) : "—"}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: profitClass }}>{t.profitPct != null ? `${t.profitPct >= 0 ? "+" : ""}${t.profitPct.toFixed(2)}%` : "—"}</div>
                    </div>
                  </div>
                  <div>
                    {MILESTONE_ORDER.map((m) => {
                      const hit = reached.includes(m);
                      const isSl = m === "sl_hit";
                      const style = hit
                        ? (isSl ? { background: "#FCEBEA", color: "#E0473F", border: "1px solid #F5C6C2" } : { background: "#EAF7F1", color: "#17A673", border: "1px solid #C7ECDA" })
                        : { background: "#F5F5F7", color: "#ADB1BC", border: "1px solid #E3E6EC" };
                      return (
                        <span key={m} style={{ display: "inline-block", padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700, marginRight: 6, ...style }}>
                          {hit ? "✓ " : ""}{MILESTONE_LABELS[m]}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* CAMPAIGN TEXT BUILDER */}
      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, marginBottom: 18 }}>
        <span style={{ fontSize: 14.5, fontWeight: 700, display: "block", marginBottom: 4 }}>Campaign text builder</span>
        <p style={{ fontSize: 12, color: "#8A90A0", margin: "0 0 14px" }}>
          Check the stocks you want in the Alert tracker card above, then compose the message here. The entry-line template repeats once per checked stock — use {"{{symbol}}"}, {"{{entry}}"}, {"{{sl}}"}, {"{{target}}"}, {"{{note}}"}, or the live Alert tracker numbers {"{{current}}"} (current price), {"{{profit}}"} (profit % from entry) and {"{{milestones}}"} (milestones reached so far). For a chart-link button, write it as {"[📊 View Chart]({{chart_url}})"} — shows a clean clickable "View Chart" label, never the raw link.
        </p>

        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 16, flexWrap: "wrap" }}>
          <label style={{ flex: 1, minWidth: 220 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Load saved template</span>
            <select value={selectedTemplateId} onChange={(e) => onTemplateSelect(e.target.value)} style={{ ...inputStyle, width: "100%" }}>
              <option value="">— Start blank —</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <button type="button" disabled={!selectedTemplateId} onClick={deleteTemplate} style={{ background: "#FCEBEA", color: "#E0473F", border: "none", borderRadius: 8, padding: "9px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", opacity: selectedTemplateId ? 1 : 0.5 }}>Delete template</button>
        </div>

        <div style={{ background: "var(--accent-tint)", border: "1px solid var(--accent)", borderRadius: 12, padding: 14, marginBottom: 16 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--accent)", marginBottom: 6 }}>✨ Generate with AI</div>
          <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 8px" }}>Tip: describe the tone, audience and purpose — e.g. "Urgent momentum breakout, energetic and high-conviction", "Calm educational summary for beginner swing traders".</p>
          <textarea value={aiInstruction} onChange={(e) => setAiInstruction(e.target.value)} rows={2} style={{ ...inputStyle, width: "100%", resize: "vertical", marginBottom: 8 }} placeholder='Optional — describe what you want' />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, color: "var(--text-faint)" }}>Uses the entries selected above, today's date &amp; live market status — fills in Title, Header and Entry line template.</span>
            <button type="button" disabled={aiGenerating} onClick={generateWithAi} style={{ background: "var(--accent)", color: "white", border: "none", borderRadius: 8, padding: "9px 18px", fontSize: 12.5, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>
              {aiGenerating ? "Generating…" : "✨ Generate"}
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Notification title</span>
              <select value={titleSource} onChange={(e) => onTitleSourceChange(e.target.value)} style={{ ...inputStyle, fontSize: 11, padding: "3px 6px" }}>
                <option value="auto">Auto (based on selection)</option>
                <option value="ai" disabled={!aiCopyAvailable}>AI-generated</option>
              </select>
            </div>
            <input type="text" value={tplTitle} onChange={(e) => setTplTitle(e.target.value)} placeholder="e.g. New scanner picks" style={{ ...inputStyle, width: "100%" }} />
          </label>
          <label>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Header</span>
              <select value={headerSource} onChange={(e) => onHeaderSourceChange(e.target.value)} style={{ ...inputStyle, fontSize: 11, padding: "3px 6px" }}>
                <option value="auto">Auto (based on selection)</option>
                <option value="ai" disabled={!aiCopyAvailable}>AI-generated</option>
              </select>
            </div>
            <textarea value={tplHeader} onChange={(e) => setTplHeader(e.target.value)} rows={2} style={{ ...inputStyle, width: "100%", resize: "vertical" }} placeholder="Intro line, e.g. Today's EMA breakout picks:" />
          </label>
          <label><span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Entry line template</span>
            <input type="text" value={tplLine} onChange={(e) => setTplLine(e.target.value)} style={{ ...inputStyle, width: "100%" }} />
          </label>
          <label><span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 5 }}>Footer</span>
            <textarea value={tplFooter} onChange={(e) => setTplFooter(e.target.value)} rows={2} style={{ ...inputStyle, width: "100%", resize: "vertical" }} />
          </label>
        </div>

        <div style={{ marginTop: 16, maxWidth: 380 }}>
          <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>Preview — how it lands in a subscriber's notification bell</span>
          <div className="notif-preview-frame">
            {!previewHtml ? (
              <div className="notif-preview-placeholder">Select entries to see a preview.</div>
            ) : (
              <div className="notif-card">
                <div className="notif-card-icon">🔔</div>
                <div className="notif-card-body">
                  <div className="notif-card-top"><span className="notif-card-title">{escapeHtml(previewHtml.title)}</span><span className="notif-card-time">now</span></div>
                  <div className="notif-card-message" dangerouslySetInnerHTML={{ __html: previewHtml.bodyHtml }} />
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "end", marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
          <label style={{ flex: 1, minWidth: 220 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 4 }}>Save this as a reusable template</span>
            <input type="text" value={templateNameInput} onChange={(e) => setTemplateNameInput(e.target.value)} style={{ ...inputStyle, width: "100%" }} placeholder='Name it, e.g. "Momentum Breakout Alert"' />
          </label>
          <button type="button" onClick={saveTemplate} style={{ background: "#14171F", color: "white", border: "none", borderRadius: 8, padding: "10px 18px", fontSize: 12.5, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>💾 Save as template</button>
        </div>

        <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
          <span style={{ fontSize: 11.5, fontWeight: 600, display: "block", marginBottom: 8 }}>Audience</span>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {[["free", "Free"], ["pro", "Pro"], ["premium", "Premium"]].map(([key, label]) => (
              <label key={key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
                <input type="checkbox" checked={audience[key]} onChange={(e) => setAudience((a) => ({ ...a, [key]: e.target.checked }))} /> {label}
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", gap: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
              <input type="checkbox" checked={channels.inApp} onChange={(e) => setChannels((c) => ({ ...c, inApp: e.target.checked }))} /> In-app notification (free, works now)
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, color: pushConfigured ? undefined : "#C0C4CC" }}>
              <input type="checkbox" disabled={!pushConfigured} checked={channels.push} onChange={(e) => setChannels((c) => ({ ...c, push: e.target.checked }))} />
              Push notification {pushConfigured ? `(${pushTokenCount} subscribed device${pushTokenCount !== 1 ? "s" : ""})` : "(not set up yet)"}
            </label>
          </div>
          <button type="button" disabled={sending} onClick={sendCampaign} style={{ background: "#4640DE", color: "white", border: "none", borderRadius: 9, padding: "11px 24px", fontSize: 13.5, fontWeight: 700, cursor: "pointer" }}>
            {sending ? "Sending…" : "Send to audience"}
          </button>
        </div>
      </div>

      {/* HISTORY */}
      <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 14.5, fontWeight: 700 }}>Recent campaigns</span>
          <button type="button" disabled={!notificationsSelected.size} onClick={deleteSelectedNotifications} style={{ background: "#FCEBEA", color: "#E0473F", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", opacity: notificationsSelected.size ? 1 : 0.5 }}>Delete selected</button>
        </div>
        <div className="table-wrap">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #E3E6EC" }}>
              <th style={{ padding: "8px 10px", width: 28 }}>
                <input type="checkbox" checked={notifications.length > 0 && notificationsSelected.size === notifications.length} onChange={(e) => setNotificationsSelected(e.target.checked ? new Set(notifications.map((n) => n.id)) : new Set())} />
              </th>
              {["Title", "Channels", "Audience", "Recipients", "Sent by", "Sent", ""].map((h) => (
                <th key={h} style={{ padding: "8px 10px", fontSize: 11, color: "#8A90A0", textTransform: "uppercase", textAlign: "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!notifications.length ? (
              <tr><td colSpan={8} style={{ padding: 20, textAlign: "center", fontSize: 13, color: "#8A90A0" }}>No campaigns sent yet.</td></tr>
            ) : (
              notifications.map((n) => (
                <tr key={n.id} style={{ borderBottom: "1px solid #F0F1F4" }}>
                  <td style={{ padding: 10 }}><input type="checkbox" checked={notificationsSelected.has(n.id)} onChange={() => toggleNotificationSelected(n.id)} /></td>
                  <td style={{ padding: 10, fontSize: 13, fontWeight: 600 }}>{n.title}</td>
                  <td style={{ padding: 10, fontSize: 12, color: "#5B6270" }}>{n.channels.join(", ")}</td>
                  <td style={{ padding: 10, fontSize: 12, color: "#5B6270", textTransform: "capitalize" }}>{(n.audience || ["free", "pro", "premium"]).join(", ")}</td>
                  <td style={{ padding: 10, fontSize: 13 }}>{n.recipient_count}</td>
                  <td style={{ padding: 10, fontSize: 12, color: "#8A90A0" }}>{n.sent_by}</td>
                  <td style={{ padding: 10, fontSize: 12, color: "#8A90A0" }}>{n.sent_at.slice(0, 16).replace("T", " ")}</td>
                  <td style={{ padding: 10 }}>
                    <button type="button" onClick={() => deleteNotification(n.id)} style={{ background: "#FCEBEA", color: "#E0473F", border: "none", fontSize: 11.5, fontWeight: 700, padding: "4px 10px", borderRadius: 6, cursor: "pointer" }}>Delete</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
