import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client";

// Ported from templates/ipo_hub.html. New GET /api/ipo-hub (app.py)
// mirrors the ipo_hub() route's logic exactly. Tab/segment filtering and
// the details modal are now React state instead of direct DOM
// manipulation, but the same three tag-buckets and filter rules.

function IpoCard({ ipo, onDetails }) {
  const mainboard = ipo.segment === "Mainboard";
  return (
    <div style={{ background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 16, padding: 22, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: ipo.logoBg, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 700, fontSize: 13 }}>
            {ipo.initials}
          </div>
          <div>
            <span style={{ fontSize: 15, fontWeight: 700, display: "block", marginBottom: 3 }}>{ipo.name}</span>
            <span style={{ background: mainboard ? "#EEEDFD" : "#FBF2E1", color: mainboard ? "#4640DE" : "#B98A2E", fontSize: 10.5, fontWeight: 700, padding: "2px 8px", borderRadius: 100, textTransform: "uppercase", letterSpacing: "0.03em" }}>
              {ipo.segment}
            </span>
          </div>
        </div>
        <span style={{ background: ipo.tagBg, color: ipo.tagColor, fontSize: 11.5, fontWeight: 700, padding: "5px 10px", borderRadius: 100 }}>{ipo.tag}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div><span style={{ fontSize: 11.5, color: "#8A90A0", display: "block" }}>Price band</span><span className="num" style={{ fontSize: 14, fontWeight: 600 }}>{ipo.priceBand}</span></div>
        <div><span style={{ fontSize: 11.5, color: "#8A90A0", display: "block" }}>Lot size</span><span className="num" style={{ fontSize: 14, fontWeight: 600 }}>{ipo.lot}</span></div>
        <div><span style={{ fontSize: 11.5, color: "#8A90A0", display: "block" }}>GMP</span><span className="num" style={{ fontSize: 14, fontWeight: 700, color: "#17A673" }}>{ipo.gmp}</span></div>
      </div>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#5B6270", marginBottom: 6 }}>
          <span>Subscribed</span><span style={{ fontWeight: 600 }}>{ipo.subLabel}</span>
        </div>
        <div style={{ width: "100%", height: 6, background: "#F0F1F4", borderRadius: 100 }}>
          <div style={{ width: ipo.subPct, height: 6, background: "#4640DE", borderRadius: 100 }} />
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: "1px solid #F0F1F4" }}>
        <span style={{ fontSize: 12, color: "#8A90A0" }}>Closes {ipo.closes}</span>
        <button type="button" onClick={() => onDetails(ipo)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 13, fontWeight: 700, color: "#4640DE" }}>
          Details →
        </button>
      </div>
    </div>
  );
}

function IpoDetailsModal({ ipo, onClose }) {
  const mainboard = ipo.segment === "Mainboard";
  return (
    <div className="modal-backdrop" style={{ background: "rgba(20,23,31,0.45)" }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: "#FFFFFF", borderRadius: 18, maxWidth: 480, width: "100%", padding: 28, position: "relative" }}>
        <button type="button" aria-label="Close" onClick={onClose} style={{ position: "absolute", top: 18, right: 18, background: "none", border: "none", cursor: "pointer", fontSize: 20, lineHeight: 1, color: "#8A90A0" }}>
          &times;
        </button>
        <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 18 }}>
          <div style={{ width: 46, height: 46, borderRadius: 12, background: ipo.logoBg, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 800, fontSize: 15, flexShrink: 0 }}>
            {ipo.initials}
          </div>
          <div>
            <span style={{ fontSize: 18, fontWeight: 800, display: "block" }}>{ipo.name}</span>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 100, textTransform: "uppercase", letterSpacing: "0.03em", background: mainboard ? "#EEEDFD" : "#FBF2E1", color: mainboard ? "#4640DE" : "#B98A2E" }}>
              {ipo.segment}
            </span>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 100, marginLeft: 6, background: ipo.tagBg, color: ipo.tagColor }}>{ipo.tag}</span>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 16, padding: "16px 0", borderTop: "1px solid #F0F1F4", borderBottom: "1px solid #F0F1F4", marginBottom: 16 }}>
          <div><span style={{ fontSize: 11, color: "#8A90A0", display: "block" }}>Price band</span><span className="num" style={{ fontSize: 14, fontWeight: 700 }}>{ipo.priceBand}</span></div>
          <div><span style={{ fontSize: 11, color: "#8A90A0", display: "block" }}>Lot size</span><span className="num" style={{ fontSize: 14, fontWeight: 700 }}>{ipo.lot}</span></div>
          <div><span style={{ fontSize: 11, color: "#8A90A0", display: "block" }}>GMP</span><span className="num" style={{ fontSize: 14, fontWeight: 700, color: "#17A673" }}>{ipo.gmp}</span></div>
        </div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, color: "#5B6270", marginBottom: 6 }}>
            <span>Subscribed</span><span style={{ fontWeight: 700 }}>{ipo.subLabel}</span>
          </div>
          <div style={{ width: "100%", height: 7, background: "#F0F1F4", borderRadius: 100 }}>
            <div style={{ height: 7, background: "#4640DE", borderRadius: 100, width: ipo.subPct }} />
          </div>
        </div>
        <p style={{ fontSize: 12.5, color: "#8A90A0", margin: "16px 0 0" }}>
          Closes <span style={{ fontWeight: 600, color: "#5B6270" }}>{ipo.closes}</span> — live GMP &amp; subscription data via investorgain.com.
        </p>
      </div>
    </div>
  );
}

export default function IpoHub() {
  const [data, setData] = useState(null);
  const [activeTab, setActiveTab] = useState("ongoing");
  const [segment, setSegment] = useState("All");
  const [detailsIpo, setDetailsIpo] = useState(null);

  useEffect(() => {
    apiFetch("/api/ipo-hub")
      .then((res) => res.json())
      .then(setData)
      .catch(() => setData({ unavailable: true, ipos: [] }));
  }, []);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") setDetailsIpo(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const groups = useMemo(() => {
    const ipos = data?.ipos || [];
    return {
      ongoing: ipos.filter((i) => ["Open", "Closing today"].includes(i.tag)),
      upcoming: ipos.filter((i) => i.tag === "Upcoming"),
      recent: ipos.filter((i) => i.tag === "Closed"),
    };
  }, [data]);

  if (!data) return null;
  const { unavailable } = data;

  const activeGroup = groups[activeTab];
  const filtered = segment === "All" ? activeGroup : activeGroup.filter((i) => i.segment === segment);

  return (
    <>
      <div style={{ width: "100%", padding: "48px 48px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ color: "#4640DE", fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>IPO Hub</span>
            <h1 style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>Upcoming &amp; ongoing IPOs</h1>
          </div>
        </div>

        {!unavailable && (
          <div style={{ maxWidth: 1200, margin: "28px auto 0", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className={"pill-tab" + (activeTab === "ongoing" ? " active" : "")} onClick={() => setActiveTab("ongoing")}>
                Ongoing ({groups.ongoing.length})
              </button>
              <button type="button" className={"pill-tab" + (activeTab === "upcoming" ? " active" : "")} onClick={() => setActiveTab("upcoming")}>
                Upcoming ({groups.upcoming.length})
              </button>
              <button type="button" className={"pill-tab" + (activeTab === "recent" ? " active" : "")} onClick={() => setActiveTab("recent")}>
                Recently Listed ({groups.recent.length})
              </button>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {["All", "Mainboard", "SME"].map((seg) => (
                <button key={seg} type="button" className={"pill-tab" + (segment === seg ? " active" : "")} onClick={() => setSegment(seg)}>
                  {seg === "All" ? "All types" : seg}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {unavailable ? (
        <div style={{ width: "100%", padding: "64px 48px" }}>
          <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", background: "#FFFFFF", border: "1px solid #E3E6EC", borderRadius: 18, padding: "48px 36px" }}>
            <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 8px" }}>Live IPO data temporarily unavailable</h2>
            <p style={{ fontSize: 14, color: "#5B6270", lineHeight: 1.6, margin: 0 }}>We couldn't reach the IPO/GMP data source just now. Please try again shortly.</p>
          </div>
        </div>
      ) : (
        <div style={{ width: "100%", padding: "24px 48px 0" }}>
          <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
            {activeGroup.length === 0 ? (
              <p style={{ color: "#8A90A0", fontSize: 14, padding: "24px 0" }}>No IPOs in this category right now.</p>
            ) : filtered.length === 0 ? (
              <p style={{ color: "#8A90A0", fontSize: 14, padding: "24px 0" }}>No matching IPOs for this filter.</p>
            ) : (
              filtered.map((ipo) => <IpoCard key={ipo.name} ipo={ipo} onDetails={setDetailsIpo} />)
            )}
          </div>
        </div>
      )}

      <div style={{ height: 88 }} />

      {detailsIpo && <IpoDetailsModal ipo={detailsIpo} onClose={() => setDetailsIpo(null)} />}
    </>
  );
}
