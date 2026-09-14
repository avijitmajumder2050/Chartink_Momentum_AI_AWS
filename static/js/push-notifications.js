// Push-notification opt-in: toggle switches (bell panel + bottom banner)
// share this one flow. The bottom banner auto-shows whenever THIS device
// has no record of ever deciding (no granted+registered token, no denial,
// no dismissal) — which is exactly "new device login" and "brand-new
// subscriber's first login" (a first login has no device history either),
// without needing any server-side device-fingerprinting.
(function () {
  var LS_REGISTERED = "quantile_push_registered";
  var LS_TOKEN = "quantile_push_token";
  var LS_BANNER_DISMISSED = "quantile_push_banner_dismissed";

  function ls(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function setLs(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }
  function removeLs(key) {
    try { localStorage.removeItem(key); } catch (e) {}
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggles = Array.prototype.slice.call(document.querySelectorAll("[data-push-toggle]"));
    var banner = document.getElementById("pushBanner");
    var bannerClose = document.getElementById("pushBannerClose");
    if (!toggles.length && !banner) return;
    if (!("Notification" in window) || !("serviceWorker" in navigator)) return;

    fetch("/api/push/config").then(function (r) { return r.json(); }).then(function (config) {
      if (!config.configured) return; // Firebase not set up yet — nothing to show

      function setToggles(checked, disabled) {
        toggles.forEach(function (t) {
          t.checked = checked;
          t.disabled = !!disabled;
        });
      }

      function hideBanner() {
        if (banner) banner.hidden = true;
      }

      function ensureFirebase() {
        if (!firebase.apps || !firebase.apps.length) firebase.initializeApp(config.firebaseConfig);
        return firebase.messaging();
      }

      function wireForegroundHandler() {
        ensureFirebase().onMessage(function (payload) {
          var title = (payload.notification && payload.notification.title) || "Quantile";
          var body = (payload.notification && payload.notification.body) || "";
          var ctaLabel = payload.data && payload.data.cta_label;
          try {
            // The service worker's background path gets a real action
            // BUTTON for the CTA (see app.py's generated sw.js) — the
            // Notification constructor used here (tab-focused/foreground
            // path) has no `actions` support at all in any browser, so
            // the closest equivalent is appending the label as a visible
            // line, keeping the whole notification clickable either way.
            var displayBody = ctaLabel ? (body ? body + "\n" + ctaLabel : ctaLabel) : body;
            var n = new Notification(title, { body: displayBody });
            // This path never goes through the service worker's
            // notificationclick handler, so it needs its own. The
            // click-target URL travels in the invisible `data` field
            // (server-side, from the campaign's "View Chart" CTA) rather
            // than appearing as text in `body` — a body-text URL match is
            // only a fallback for anything that didn't go through that.
            var dataUrl = payload.data && payload.data.url;
            var urlMatch = body.match(/https?:\/\/\S+/);
            var clickUrl = dataUrl || (urlMatch ? urlMatch[0] : null);
            if (clickUrl) {
              n.onclick = function () {
                window.open(clickUrl, "_blank");
                n.close();
              };
            }
          } catch (e) {}
        });
      }

      function enable() {
        setToggles(true, true);
        return navigator.serviceWorker.register("/firebase-messaging-sw.js")
          .then(function () { return navigator.serviceWorker.ready; })
          .then(function (registration) {
            return Notification.requestPermission().then(function (permission) {
              if (permission !== "granted") {
                setToggles(false, false);
                hideBanner();
                setLs(LS_BANNER_DISMISSED, "1"); // browser will silently no-op future prompts anyway
                return;
              }
              return ensureFirebase().getToken({ vapidKey: config.vapidKey, serviceWorkerRegistration: registration })
                .then(function (token) {
                  return fetch("/api/push/register-token", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: token }),
                  }).then(function (res) {
                    if (!res.ok) throw new Error("register-token failed");
                    setLs(LS_REGISTERED, "1");
                    setLs(LS_TOKEN, token);
                    setLs(LS_BANNER_DISMISSED, "1");
                    setToggles(true, false);
                    hideBanner();
                    wireForegroundHandler();
                  });
                });
            });
          })
          .catch(function (err) {
            console.error("Push opt-in failed:", err);
            setToggles(false, false);
          });
      }

      function disable() {
        setToggles(false, true);
        var token = ls(LS_TOKEN);
        var cleanup = function () {
          removeLs(LS_REGISTERED);
          removeLs(LS_TOKEN);
          setToggles(false, false);
        };
        var serverCall = token
          ? fetch("/api/push/unregister-token", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ token: token }),
            })
          : Promise.resolve();
        return serverCall.then(function () {
          try {
            if (firebase.apps && firebase.apps.length) return ensureFirebase().deleteToken();
          } catch (e) {}
        }).catch(function () {}).then(cleanup);
      }

      toggles.forEach(function (t) {
        t.addEventListener("change", function () {
          if (t.checked) enable(); else disable();
        });
      });

      if (bannerClose) {
        bannerClose.addEventListener("click", function () {
          hideBanner();
          setLs(LS_BANNER_DISMISSED, "1");
        });
      }

      // ---- Decide initial state ----
      var registeredHere = ls(LS_REGISTERED) === "1";

      if (Notification.permission === "granted" && registeredHere) {
        setToggles(true, false);
        wireForegroundHandler();
        hideBanner();
        return;
      }

      if (Notification.permission === "denied") {
        setToggles(false, true); // browser-level block — nothing a toggle here can do
        hideBanner();
        return;
      }

      // Notification.permission === "default" and not registered on this
      // device: either a device that's never opted in, or a brand-new
      // subscriber's first-ever login. Prompt via the toggle switch.
      setToggles(false, false);
      if (banner && ls(LS_BANNER_DISMISSED) !== "1") banner.hidden = false;
    }).catch(function () {});
  });
})();
