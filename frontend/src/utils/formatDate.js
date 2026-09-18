// Backend timestamps (sent_at, updated_at, etc.) are stored as naive UTC
// ISO strings (datetime.utcnow().isoformat(), no "Z"/offset suffix) — see
// connectors/campaign_connector.py. `new Date(iso)` would otherwise parse
// that as *local* time in whatever timezone the viewer's browser/OS is
// set to, silently shifting it. Every display of one of these timestamps
// should go through here so it always reads as real IST regardless of
// the viewer's own device timezone — this is a trading app, IST is the
// one timezone that means the same thing to every user.
export function formatIST(iso, options) {
  if (!iso) return "";
  const withZone = iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z";
  const d = new Date(withZone);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", ...options });
}

export function formatISTDateTime(iso) {
  return formatIST(iso, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true });
}

export function formatISTDate(iso) {
  return formatIST(iso, { day: "2-digit", month: "short", year: "numeric" });
}
