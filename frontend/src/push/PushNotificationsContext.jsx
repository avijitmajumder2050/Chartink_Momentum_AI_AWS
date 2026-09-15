import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

// Ported from static/js/push-notifications.js + templates/_push_banner.
// html. Two UI surfaces share this one flow: the notification bell's
// push-toggle row (NotificationBell.jsx) and the bottom opt-in banner
// (PushBanner.jsx) — both call toggle()/dismissBanner() from here so
// their state always agrees, same as the original's shared
// [data-push-toggle] querySelectorAll approach but via React state
// instead of a DOM collection.
//
// The bottom banner auto-shows whenever THIS device has no record of
// ever deciding (no granted+registered token, no denial, no dismissal)
// — "new device login" / "brand-new subscriber's first login", without
// any server-side device-fingerprinting.

const LS_REGISTERED = "quantile_push_registered";
const LS_TOKEN = "quantile_push_token";
const LS_BANNER_DISMISSED = "quantile_push_banner_dismissed";

function ls(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function setLs(key, value) {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
}
function removeLs(key) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

const PushNotificationsContext = createContext(null);

export function PushNotificationsProvider({ children }) {
  const { user } = useAuth();
  const [configured, setConfigured] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [toggleDisabled, setToggleDisabled] = useState(false);
  const [bannerVisible, setBannerVisible] = useState(false);
  const configRef = useRef(null); // {firebaseConfig, vapidKey}
  const firebaseLoadedRef = useRef(false);
  const foregroundWiredRef = useRef(false);

  const ensureFirebase = useCallback(async () => {
    if (!firebaseLoadedRef.current) {
      await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
      await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");
      firebaseLoadedRef.current = true;
    }
    /* global firebase */
    // eslint-disable-next-line no-undef
    if (!firebase.apps || !firebase.apps.length) firebase.initializeApp(configRef.current.firebaseConfig);
    // eslint-disable-next-line no-undef
    return firebase.messaging();
  }, []);

  const wireForegroundHandler = useCallback(async () => {
    if (foregroundWiredRef.current) return;
    foregroundWiredRef.current = true;
    const messaging = await ensureFirebase();
    messaging.onMessage((payload) => {
      const title = (payload.notification && payload.notification.title) || "Quantile";
      const body = (payload.notification && payload.notification.body) || "";
      const ctaLabel = payload.data && payload.data.cta_label;
      try {
        // The service worker's background path gets a real action BUTTON
        // for the CTA (see app.py's generated sw.js) — the Notification
        // constructor here (tab-focused/foreground path) has no `actions`
        // support in any browser, so the label is appended as a visible
        // line instead, keeping the whole notification clickable either way.
        const displayBody = ctaLabel ? (body ? `${body}\n${ctaLabel}` : ctaLabel) : body;
        const n = new Notification(title, { body: displayBody, icon: "/favicon.svg" });
        const dataUrl = payload.data && payload.data.url;
        const urlMatch = body.match(/https?:\/\/\S+/);
        const clickUrl = dataUrl || (urlMatch ? urlMatch[0] : null);
        if (clickUrl) {
          n.onclick = () => {
            window.open(clickUrl, "_blank");
            n.close();
          };
        }
      } catch { /* best-effort */ }
    });
  }, [ensureFirebase]);

  useEffect(() => {
    if (!user) return;
    if (!("Notification" in window) || !("serviceWorker" in navigator)) return;

    apiFetch("/api/push/config")
      .then((res) => res.json())
      .then((config) => {
        if (!config.configured) return;
        setConfigured(true);
        configRef.current = { firebaseConfig: config.firebaseConfig, vapidKey: config.vapidKey };

        const registeredHere = ls(LS_REGISTERED) === "1";

        if (Notification.permission === "granted" && registeredHere) {
          setEnabled(true);
          setToggleDisabled(false);
          wireForegroundHandler();
          return;
        }
        if (Notification.permission === "denied") {
          setEnabled(false);
          setToggleDisabled(true); // browser-level block — nothing a toggle here can do
          return;
        }
        // permission === "default" and not registered on this device:
        // either never opted in, or a brand-new subscriber's first login.
        setEnabled(false);
        setToggleDisabled(false);
        if (ls(LS_BANNER_DISMISSED) !== "1") setBannerVisible(true);
      })
      .catch(() => {});
  }, [user, wireForegroundHandler]);

  const enable = useCallback(() => {
    setToggleDisabled(true);
    return navigator.serviceWorker
      .register("/firebase-messaging-sw.js")
      .then(() => navigator.serviceWorker.ready)
      .then((registration) =>
        Notification.requestPermission().then((permission) => {
          if (permission !== "granted") {
            setEnabled(false);
            setToggleDisabled(false);
            setBannerVisible(false);
            setLs(LS_BANNER_DISMISSED, "1"); // browser will silently no-op future prompts anyway
            return;
          }
          return ensureFirebase()
            .then((messaging) => messaging.getToken({ vapidKey: configRef.current.vapidKey, serviceWorkerRegistration: registration }))
            .then((token) =>
              apiFetch("/api/push/register-token", { method: "POST", body: JSON.stringify({ token }) }).then((res) => {
                if (!res.ok) throw new Error("register-token failed");
                setLs(LS_REGISTERED, "1");
                setLs(LS_TOKEN, token);
                setLs(LS_BANNER_DISMISSED, "1");
                setEnabled(true);
                setToggleDisabled(false);
                setBannerVisible(false);
                wireForegroundHandler();
              })
            );
        })
      )
      .catch((err) => {
        console.error("Push opt-in failed:", err);
        setEnabled(false);
        setToggleDisabled(false);
      });
  }, [ensureFirebase, wireForegroundHandler]);

  const disable = useCallback(() => {
    setToggleDisabled(true);
    const token = ls(LS_TOKEN);
    const cleanup = () => {
      removeLs(LS_REGISTERED);
      removeLs(LS_TOKEN);
      setEnabled(false);
      setToggleDisabled(false);
    };
    const serverCall = token ? apiFetch("/api/push/unregister-token", { method: "POST", body: JSON.stringify({ token }) }) : Promise.resolve();
    return serverCall
      .then(() => {
        /* eslint-disable no-undef */
        if (typeof firebase !== "undefined" && firebase.apps && firebase.apps.length) return ensureFirebase().then((m) => m.deleteToken());
        /* eslint-enable no-undef */
      })
      .catch(() => {})
      .then(cleanup);
  }, [ensureFirebase]);

  function toggle(checked) {
    return checked ? enable() : disable();
  }

  function dismissBanner() {
    setBannerVisible(false);
    setLs(LS_BANNER_DISMISSED, "1");
  }

  return (
    <PushNotificationsContext.Provider value={{ configured, enabled, toggleDisabled, bannerVisible, toggle, dismissBanner }}>
      {children}
    </PushNotificationsContext.Provider>
  );
}

export function usePushNotifications() {
  const ctx = useContext(PushNotificationsContext);
  if (!ctx) throw new Error("usePushNotifications must be used within a PushNotificationsProvider");
  return ctx;
}
