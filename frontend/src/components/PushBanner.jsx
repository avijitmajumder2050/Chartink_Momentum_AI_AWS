import { usePushNotifications } from "../push/PushNotificationsContext";

// Ported from templates/_push_banner.html.
export default function PushBanner() {
  const push = usePushNotifications();
  if (!push.configured || !push.bannerVisible) return null;

  return (
    <div id="pushBanner" role="dialog" aria-label="Enable push notifications">
      <div className="push-banner-body">
        <div className="push-banner-title">Turn on push notifications?</div>
        <div className="push-banner-sub">Get instant alerts for new trade signals and account activity.</div>
      </div>
      <label className="toggle-switch" style={{ alignSelf: "center" }}>
        <input type="checkbox" aria-label="Enable push notifications" checked={push.enabled} disabled={push.toggleDisabled} onChange={(e) => push.toggle(e.target.checked)} />
        <span className="toggle-switch-track" />
      </label>
      <button type="button" className="push-banner-close" aria-label="Dismiss" onClick={push.dismissBanner}>
        &times;
      </button>
    </div>
  );
}
