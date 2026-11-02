/* WorkAtlas — native iOS bridge.
   Enhances the server-rendered site when it runs inside the Capacitor shell.
   The file is inert in a normal browser, so it is safe to ship to the web. */
(function () {
  "use strict";

  var Cap = window.Capacitor;
  if (!Cap || typeof Cap.isNativePlatform !== "function" || !Cap.isNativePlatform()) return;

  var root = document.documentElement;
  var LANG = (document.body && document.body.dataset.lang) || "en";
  var I18N = window.EJP_I18N || {};
  var BIO_KEY = "ejp.biometric";
  var bioEnabled = false;
  var bioAvailable = false;
  var lockEl = null;
  var hiddenAt = 0;
  var offlineBanner = null;
  var toastEl = null;
  var toastTimer = null;

  root.classList.add("native-app");

  function t(key, fallback) {
    var value = I18N[key];
    return value === undefined || value === null || value === "" ? fallback || key : value;
  }

  function plugin(name) {
    try {
      return (Cap.Plugins && Cap.Plugins[name]) || null;
    } catch (error) {
      return null;
    }
  }

  function safe(promise) {
    if (promise && typeof promise.catch === "function") return promise.catch(function () {});
    return promise;
  }

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  function appBase() {
    return (window.EJP_APP_URL || location.origin || "").replace(/\/+$/, "");
  }

  function isDark() {
    var theme = root.dataset.theme;
    if (theme === "dark") return true;
    if (theme === "light") return false;
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function syncStatusBar() {
    var status = plugin("StatusBar");
    if (status && status.setStyle) {
      safe(status.setStyle({ style: isDark() ? "LIGHT" : "DARK" }));
    }
    var themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) themeMeta.setAttribute("content", isDark() ? "#0b1220" : "#fbfbfd");
  }

  function toast(message) {
    if (!message) return;
    if (toastEl && toastEl.parentNode) toastEl.parentNode.removeChild(toastEl);
    toastEl = document.createElement("div");
    toastEl.className = "native-toast";
    toastEl.textContent = message;
    document.body.appendChild(toastEl);
    window.requestAnimationFrame(function () {
      toastEl.classList.add("is-visible");
    });
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      if (!toastEl) return;
      toastEl.classList.remove("is-visible");
      window.setTimeout(function () {
        if (toastEl && toastEl.parentNode) toastEl.parentNode.removeChild(toastEl);
        toastEl = null;
      }, 260);
    }, 2600);
  }

  /* ------------------------------------------------------------------ */
  /* Offline state                                                      */
  /* ------------------------------------------------------------------ */

  function ensureBanner() {
    if (offlineBanner) return offlineBanner;
    offlineBanner = document.createElement("div");
    offlineBanner.className = "native-banner";
    offlineBanner.hidden = true;
    offlineBanner.innerHTML = '<span class="dot"></span><span></span>';
    document.body.appendChild(offlineBanner);
    return offlineBanner;
  }

  function setOffline(offline, announce) {
    var wasOffline = !ensureBanner().hidden;
    var banner = ensureBanner();
    banner.hidden = !offline;
    banner.lastElementChild.textContent = t(
      "native.offline",
      "You are offline. Some live results may be unavailable."
    );
    if (announce && wasOffline && !offline) toast(t("native.online", "Back online"));
  }

  function setupNetwork() {
    var network = plugin("Network");
    if (!network) return;
    network.getStatus().then(function (status) {
      setOffline(!(status && status.connected), false);
    }).catch(function () {});
    if (network.addListener) {
      network.addListener("networkStatusChange", function (status) {
        setOffline(!(status && status.connected), true);
      });
    }
  }

  /* ------------------------------------------------------------------ */
  /* Links, sharing and file exports                                    */
  /* ------------------------------------------------------------------ */

  function openExternal(url) {
    var browser = plugin("Browser");
    if (browser && browser.open) {
      safe(browser.open({ url: url, presentationStyle: "fullscreen" }));
    } else {
      window.location.href = url;
    }
  }

  function handleAppUrl(raw) {
    if (!raw) return;
    var url = String(raw);
    if (url.indexOf("workatlas://") === 0) {
      url = appBase() + "/" + url.slice("workatlas://".length).replace(/^\/+/, "");
    }
    try {
      var target = new URL(url, location.href);
      if (target.origin === location.origin) {
        window.location.href = target.href;
      } else {
        openExternal(target.href);
      }
    } catch (error) {
      /* ignore malformed links */
    }
  }

  function setupShare() {
    document.addEventListener("click", function (event) {
      var button = event.target && event.target.closest
        ? event.target.closest("[data-native-share]")
        : null;
      if (!button) return;
      event.preventDefault();
      var share = plugin("Share");
      if (!share || !share.share) {
        toast(t("native.share_failed", "Sharing is unavailable right now."));
        return;
      }
      safe(
        share.share({
          title: button.dataset.shareTitle || document.title,
          text: button.dataset.shareText || "",
          url: button.dataset.shareUrl || location.href,
          dialogTitle: button.dataset.shareTitle || document.title
        })
      ).then(function (result) {
        if (result && result.activityType === undefined) return;
      });
    });
  }

  function base64FromBuffer(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = "";
    var chunk = 0x8000;
    for (var i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return window.btoa(binary);
  }

  function filenameFor(disposition, url) {
    var match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition || "");
    var name = match ? decodeURIComponent(match[1].replace(/"/g, "").trim()) : "";
    if (!name) {
      var path = url.split("?")[0].split("/");
      name = "workatlas-" + (path[path.length - 2] || "document") + "." + (path[path.length - 1] || "pdf").split(".").pop();
    }
    return name.replace(/[^\w.\-]+/g, "-").slice(0, 120);
  }

  function downloadFile(url) {
    var files = plugin("Filesystem");
    var share = plugin("Share");
    if (!files || !files.writeFile) {
      window.location.href = url;
      return Promise.resolve();
    }
    return fetch(url, { credentials: "include" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        var name = filenameFor(response.headers.get("content-disposition"), url);
        return response.arrayBuffer().then(function (buffer) {
          return files
            .writeFile({
              path: name,
              data: base64FromBuffer(buffer),
              directory: "CACHE",
              encoding: "base64"
            })
            .then(function () {
              return files.getUri({ path: name, directory: "CACHE" });
            })
            .then(function (uri) {
              if (share && share.share) {
                return share.share({ title: name, url: uri.uri });
              }
              return null;
            });
        });
      })
      .then(function () {
        toast(t("native.download_saved", "File ready. Choose where to save it."));
      });
  }

  function setupDownloads() {
    document.addEventListener("click", function (event) {
      var link = event.target && event.target.closest
        ? event.target.closest("a[data-native-download]")
        : null;
      if (!link) return;
      var href = link.getAttribute("href") || "";
      if (!/\/export\.(pdf|docx)$/i.test(href)) return;
      event.preventDefault();
      downloadFile(href).catch(function () {
        toast(t("native.download_failed", "The file could not be saved."));
      });
    });
  }

  function setupHaptics() {
    document.addEventListener(
      "submit",
      function (event) {
        var form = event.target;
        var action = (form && form.getAttribute("action")) || "";
        if (action.indexOf("/saved/") === -1) return;
        var haptics = plugin("Haptics");
        if (haptics && haptics.impact) safe(haptics.impact({ style: "light" }));
      },
      true
    );
  }

  /* ------------------------------------------------------------------ */
  /* Biometric app lock                                                 */
  /* ------------------------------------------------------------------ */

  function preferenceGet(key) {
    var prefs = plugin("Preferences");
    if (!prefs || !prefs.get) return Promise.resolve(null);
    return prefs.get({ key: key }).then(function (result) {
      return result ? result.value : null;
    }).catch(function () {
      return null;
    });
  }

  function preferenceSet(key, value) {
    var prefs = plugin("Preferences");
    if (prefs && prefs.set) safe(prefs.set({ key: key, value: value }));
  }

  function preferenceRemove(key) {
    var prefs = plugin("Preferences");
    if (prefs && prefs.remove) safe(prefs.remove({ key: key }));
  }

  function authenticate() {
    var bio = plugin("BiometricAuth");
    if (!bio || !bio.authenticate) return Promise.reject(new Error("unavailable"));
    return bio.authenticate({
      reason: t("native.biometric_prompt", "Unlock WorkAtlas to protect your CV and saved jobs."),
      cancelTitle: t("native.biometric_cancel", "Cancel"),
      iosFallbackTitle: t("native.unlock", "Unlock"),
      allowDeviceCredential: true
    });
  }

  function removeLock() {
    if (lockEl && lockEl.parentNode) lockEl.parentNode.removeChild(lockEl);
    lockEl = null;
  }

  function lockApp() {
    if (!bioEnabled || lockEl) return;
    lockEl = document.createElement("div");
    lockEl.className = "native-lock";
    lockEl.innerHTML =
      '<div class="native-lock-inner">' +
      '<svg class="native-lock-mark" viewBox="0 0 96 96" aria-hidden="true">' +
      '<rect width="96" height="96" rx="22" fill="#0b1220"/>' +
      '<g fill="#0a84ff">' +
      '<circle cx="48" cy="18" r="3.4"/><circle cx="61" cy="21.5" r="3.4"/>' +
      '<circle cx="70.5" cy="31" r="3.4"/><circle cx="74" cy="44" r="3.4"/>' +
      '<circle cx="70.5" cy="57" r="3.4"/><circle cx="61" cy="66.5" r="3.4"/>' +
      '<circle cx="48" cy="70" r="3.4"/><circle cx="35" cy="66.5" r="3.4"/>' +
      '<circle cx="25.5" cy="57" r="3.4"/><circle cx="22" cy="44" r="3.4"/>' +
      '<circle cx="25.5" cy="31" r="3.4"/><circle cx="35" cy="21.5" r="3.4"/>' +
      "</g>" +
      '<path d="M38 48h20M38 40h14M38 56h14" stroke="#f5f5f7" stroke-width="4" stroke-linecap="round"/>' +
      "</svg>" +
      "<h2></h2><p></p>" +
      '<button class="btn btn-primary" type="button"></button>' +
      "</div>";
    lockEl.querySelector("h2").textContent = t("native.lock_title", "WorkAtlas is locked");
    lockEl.querySelector("p").textContent = t(
      "native.lock_body",
      "Use Face ID or your passcode to continue."
    );
    lockEl.querySelector("button").textContent = t("native.unlock", "Unlock");
    lockEl.querySelector("button").addEventListener("click", attemptUnlock);
    document.body.appendChild(lockEl);
    attemptUnlock();

    function attemptUnlock() {
      authenticate().then(removeLock).catch(function () {
        /* The system prompt can be cancelled; keep the lock visible. */
      });
    }
  }

  function setupBiometric() {
    var bio = plugin("BiometricAuth");
    if (!bio || !bio.checkBiometry) return;
    var card = document.getElementById("native-device-card");
    if (card) card.hidden = false;
    var toggle = document.querySelector("[data-biometric-toggle]");
    var note = document.querySelector("[data-biometric-note]");

    bio.checkBiometry().then(function (info) {
      bioAvailable = !!(info && (info.isAvailable || info.deviceIsSecure));
      if (!bioAvailable) {
        if (toggle) {
          toggle.checked = false;
          toggle.disabled = true;
        }
        if (note) note.textContent = t("native.biometric_unavailable", "Biometric unlock is not available on this device.");
        return null;
      }
      if (note) note.textContent = t("native.biometric_note", "The lock protects this device only.");
      return preferenceGet(BIO_KEY).then(function (value) {
        bioEnabled = value === "1";
        if (toggle) toggle.checked = bioEnabled;
        if (bioEnabled) lockApp();
      });
    }).catch(function () {});

    if (toggle) {
      toggle.addEventListener("change", function () {
        if (toggle.checked) {
          authenticate().then(function () {
            bioEnabled = true;
            preferenceSet(BIO_KEY, "1");
            toast(t("native.biometric_enable", "Unlock with Face ID or Touch ID"));
          }).catch(function () {
            bioEnabled = false;
            toggle.checked = false;
            preferenceRemove(BIO_KEY);
          });
        } else {
          bioEnabled = false;
          preferenceRemove(BIO_KEY);
          removeLock();
          toast(t("native.biometric_disable", "App lock disabled"));
        }
      });
    }
  }

  /* ------------------------------------------------------------------ */
  /* Push notifications (only shown when the server has APNs configured) */
  /* ------------------------------------------------------------------ */

  function setupPush(config) {
    if (!config || !config.push_enabled) return;
    var push = plugin("PushNotifications");
    if (!push) return;
    var block = document.querySelector("[data-push-block]");
    var button = document.querySelector("[data-push-enable]");
    var note = document.querySelector("[data-push-note]");
    if (block) block.hidden = false;

    function register() {
      push.requestPermissions().then(function (result) {
        if (result && result.receive === "granted") {
          push.register();
        } else if (note) {
          note.textContent = t("native.push_denied", "Notifications are disabled. Enable them in iOS Settings.");
        }
      }).catch(function () {});
    }

    if (button) button.addEventListener("click", register);

    if (push.addListener) {
      push.addListener("registration", function (token) {
        var meta = document.querySelector('meta[name="csrf-token"]');
        fetch("/api/push/register", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            token: token && token.value,
            platform: "ios",
            locale: LANG,
            csrf: meta ? meta.content : ""
          })
        }).then(function (response) {
          if (response.ok && note) note.textContent = t("native.push_enabled", "Notifications are on for this device.");
        }).catch(function () {});
      });
      push.addListener("registrationError", function () {
        if (note) note.textContent = t("native.push_denied", "Notifications are disabled. Enable them in iOS Settings.");
      });
      push.addListener("pushNotificationActionPerformed", function (action) {
        var data = action && action.notification && action.notification.data;
        if (data && data.url) handleAppUrl(data.url);
      });
    }
  }

  function loadConfig() {
    return fetch("/api/app/config", {
      credentials: "include",
      headers: { Accept: "application/json" }
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).catch(function () {
      return null;
    });
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                               */
  /* ------------------------------------------------------------------ */

  ready(function () {
    syncStatusBar();
    if (window.MutationObserver) {
      new MutationObserver(syncStatusBar).observe(root, {
        attributes: true,
        attributeFilter: ["data-theme"]
      });
    }
    setupNetwork();
    setupShare();
    setupDownloads();
    setupHaptics();
    setupBiometric();
    loadConfig().then(setupPush);

    var app = plugin("App");
    if (app && app.addListener) {
      app.addListener("appStateChange", function (state) {
        if (!bioEnabled) return;
        if (state && state.isActive) {
          if (hiddenAt && Date.now() - hiddenAt > 60000) lockApp();
          hiddenAt = 0;
        } else {
          hiddenAt = Date.now();
        }
      });
      app.addListener("appUrlOpen", function (event) {
        handleAppUrl(event && event.url);
      });
    }
  });

  window.addEventListener("load", function () {
    var splash = plugin("SplashScreen");
    if (splash && splash.hide) safe(splash.hide());
  });
})();
