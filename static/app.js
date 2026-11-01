/* EuroJobs Pro — client behaviour
   Theme switching, navigation, filters, saved listings, live results and the
   streaming assistant. No framework, no build step, no third-party requests. */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var I18N = window.EJP_I18N || {};
  var LANG = window.EJP_LANG || "en";

  function t(key, fallback) {
    var value = I18N[key];
    return value === undefined || value === null || value === "" ? fallback || key : value;
  }

  function on(target, event, handler, options) {
    if (target) target.addEventListener(event, handler, options);
  }

  function escapeHtml(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* ------------------------------------------------------------------ */
  /* Theme                                                              */
  /* ------------------------------------------------------------------ */

  var THEMES = ["light", "dark", "system"];
  var storedTheme = null;
  try {
    storedTheme = localStorage.getItem("ejp-theme");
  } catch (error) {
    storedTheme = null;
  }

  function systemDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function applyTheme(theme, persist) {
    var value = THEMES.indexOf(theme) === -1 ? "system" : theme;
    root.dataset.theme = value;
    if (persist) {
      try {
        localStorage.setItem("ejp-theme", value);
      } catch (error) {
        /* private mode */
      }
      doc.cookie = "ejp_theme=" + value + "; path=/; max-age=31536000; samesite=lax";
    }
    Array.prototype.forEach.call(doc.querySelectorAll("[data-theme-set]"), function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.themeSet === value));
    });
  }

  if (storedTheme && THEMES.indexOf(storedTheme) !== -1) {
    applyTheme(storedTheme, false);
  } else {
    applyTheme(root.dataset.theme || "system", false);
  }

  Array.prototype.forEach.call(doc.querySelectorAll("[data-theme-set]"), function (button) {
    on(button, "click", function () {
      applyTheme(button.dataset.themeSet, true);
    });
  });

  if (window.matchMedia) {
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      if (root.dataset.theme === "system") applyTheme("system", false);
    };
    if (query.addEventListener) query.addEventListener("change", onChange);
    else if (query.addListener) query.addListener(onChange);
  }

  /* ------------------------------------------------------------------ */
  /* Navigation                                                         */
  /* ------------------------------------------------------------------ */

  var toggle = doc.querySelector(".nav-toggle");
  var mobileMenu = doc.getElementById("mobile-menu");
  if (toggle && mobileMenu) {
    on(toggle, "click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      mobileMenu.classList.toggle("is-open", !open);
    });
  }

  var langSwitch = doc.querySelector(".lang-switch");
  if (langSwitch) {
    on(doc, "click", function (event) {
      if (!langSwitch.contains(event.target)) langSwitch.removeAttribute("open");
    });
  }

  /* ------------------------------------------------------------------ */
  /* Toasts                                                             */
  /* ------------------------------------------------------------------ */

  Array.prototype.forEach.call(doc.querySelectorAll(".toast"), function (toast) {
    window.setTimeout(function () {
      toast.style.transition = "opacity .4s ease, transform .4s ease";
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-8px)";
      window.setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 450);
    }, 6500);
  });

  /* ------------------------------------------------------------------ */
  /* Confirmation dialogs                                               */
  /* ------------------------------------------------------------------ */

  Array.prototype.forEach.call(doc.querySelectorAll("form[data-confirm]"), function (form) {
    on(form, "submit", function (event) {
      var message = form.getAttribute("data-confirm") || t("common.confirm", "Are you sure?");
      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    });
  });

  /* ------------------------------------------------------------------ */
  /* Saved listings                                                     */
  /* ------------------------------------------------------------------ */

  Array.prototype.forEach.call(doc.querySelectorAll("form[data-save]"), function (form) {
    on(form, "submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      var svg = button ? button.querySelector("svg") : null;
      if (button) button.disabled = true;
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (response) {
          if (!response.ok) throw new Error("save failed");
          return response.json();
        })
        .then(function (data) {
          if (!button) return;
          button.setAttribute("aria-pressed", String(Boolean(data.saved)));
          if (svg) svg.setAttribute("fill", data.saved ? "currentColor" : "none");
        })
        .catch(function () {
          /* Leave the button unchanged; the next page load is authoritative. */
        })
        .finally(function () {
          if (button) button.disabled = false;
        });
    });
  });

  /* ------------------------------------------------------------------ */
  /* Load more / infinite scroll                                        */
  /* ------------------------------------------------------------------ */

  var loadMore = doc.getElementById("load-more");
  var results = doc.getElementById("results");
  var loading = false;

  function nextPageUrl(url) {
    try {
      var parsed = new URL(url, window.location.origin);
      var page = parseInt(parsed.searchParams.get("page") || "2", 10);
      parsed.searchParams.set("page", String(page + 1));
      return parsed.pathname + "?" + parsed.searchParams.toString();
    } catch (error) {
      return url;
    }
  }

  function fetchMore() {
    if (!loadMore || loading) return;
    var url = loadMore.getAttribute("data-next");
    if (!url) return;
    loading = true;
    loadMore.disabled = true;
    var separator = url.indexOf("?") === -1 ? "?" : "&";
    fetch(url + separator + "partial=1", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("load failed");
        return response.json();
      })
      .then(function (data) {
        if (results && data.html) results.insertAdjacentHTML("beforeend", data.html);
        if (!data.has_more) {
          loadMore.parentNode.removeChild(loadMore);
          loadMore = null;
          return;
        }
        loadMore.setAttribute("data-next", nextPageUrl(url));
        loadMore.setAttribute("data-loaded", String(data.page || ""));
      })
      .catch(function () {
        /* Keep the manual button available for another try. */
      })
      .finally(function () {
        loading = false;
        if (loadMore) loadMore.disabled = false;
      });
  }

  if (loadMore) {
    on(loadMore, "click", fetchMore);
    if ("IntersectionObserver" in window && results) {
      var sentinel = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) fetchMore();
          });
        },
        { rootMargin: "400px 0px" }
      );
      sentinel.observe(loadMore);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Live augmentation                                                  */
  /* ------------------------------------------------------------------ */

  var livePanel = doc.getElementById("live-results");
  if (livePanel && livePanel.dataset.query) {
    var liveQuery = livePanel.dataset.query;
    var liveCards = doc.getElementById("live-cards");
    fetch("/api/live?type=job&q=" + encodeURIComponent(liveQuery), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("live failed");
        return response.json();
      })
      .then(function (data) {
        var items = (data && data.items) || [];
        if (!items.length || !liveCards) return;
        liveCards.innerHTML = items.map(liveCard).join("");
        livePanel.hidden = false;
      })
      .catch(function () {
        /* Live results are optional; stored results remain. */
      });
  }

  function liveCard(card) {
    var kind = card.type === "volunteer" ? "volunteer" : "jobs";
    var tier = Number(card.visa_tier) === 1;
    var badge = kind === "volunteer"
      ? t(tier ? "volunteer.support_confirmed" : "volunteer.support_mentioned")
      : t(tier ? "visa.verified_sponsor" : "visa.sponsorship_mentioned");
    var location = [card.city, card.country_code ? t("country." + String(card.country_code).toLowerCase(), card.country) : card.country]
      .filter(Boolean)
      .join(" · ");
    return (
      '<article class="job-card">' +
      '<div class="card-top">' +
      (card.logo ? '<img class="card-logo" src="' + escapeHtml(card.logo) + '" alt="" width="44" height="44" loading="lazy">' : "") +
      '<div class="card-heading"><h3><a href="/' + kind + "/" + escapeHtml(card.id) + '">' + escapeHtml(card.title) + "</a></h3>" +
      '<p class="card-company">' + escapeHtml(card.company) + "</p></div></div>" +
      (location ? '<p class="card-meta"><span>' + escapeHtml(location) + "</span></p>" : "") +
      '<div class="card-badges"><span class="badge ' + (tier ? "badge-verified" : "badge-mentioned") + '">' + escapeHtml(badge) + "</span></div>" +
      '<div class="card-actions">' +
      '<a class="btn btn-primary btn-sm" href="' + escapeHtml(card.apply_url || "/" + kind + "/" + card.id) + '" rel="nofollow noopener" target="_blank">' + escapeHtml(t("common.apply_now")) + "</a>" +
      '<a class="link link-arrow" href="/' + kind + "/" + escapeHtml(card.id) + '">' + escapeHtml(t("common.details")) + " ›</a>" +
      "</div></article>"
    );
  }

  /* ------------------------------------------------------------------ */
  /* Assistant                                                          */
  /* ------------------------------------------------------------------ */

  var agent = doc.getElementById("agent");
  if (!agent) return;

  var launch = doc.getElementById("agent-launch");
  var panel = doc.getElementById("agent-panel");
  var close = doc.getElementById("agent-close");
  var log = doc.getElementById("agent-log");
  var form = doc.getElementById("agent-form");
  var input = doc.getElementById("agent-input");
  var send = doc.getElementById("agent-send");
  var stopButton = doc.getElementById("agent-stop");
  var clearButton = doc.getElementById("agent-clear");
  var quotaLine = doc.getElementById("agent-quota");
  var csrf = agent.dataset.csrf || "";
  var chatSession = agent.dataset.session || "";
  var controller = null;
  var pending = false;

  function scrollLog() {
    if (log) log.scrollTop = log.scrollHeight;
  }

  function openPanel() {
    if (!panel) return;
    panel.hidden = false;
    if (launch) launch.setAttribute("aria-expanded", "true");
    if (input) input.focus();
    if (!chatSession) ensureSession();
  }

  function closePanel() {
    if (!panel) return;
    panel.hidden = true;
    if (launch) {
      launch.setAttribute("aria-expanded", "false");
      launch.focus();
    }
  }

  function ensureSession() {
    if (chatSession) return Promise.resolve(chatSession);
    return fetch("/api/agent/session", {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("session failed");
        return response.json();
      })
      .then(function (data) {
        chatSession = (data && data.session) || "";
        agent.dataset.session = chatSession;
        return chatSession;
      })
      .catch(function () {
        addMessage("assistant", t("agent.error"), true);
        return "";
      });
  }

  function addMessage(role, text, isError) {
    if (!log) return null;
    var bubble = doc.createElement("div");
    bubble.className = "agent-msg " + (isError ? "error" : role);
    renderInto(bubble, text);
    log.appendChild(bubble);
    scrollLog();
    return bubble;
  }

  function renderInto(node, text) {
    var escaped = escapeHtml(text || "");
    escaped = escaped.replace(/(https?:\/\/[^\s<]+)/g, function (url) {
      return '<a href="' + url + '" rel="noopener noreferrer nofollow" target="_blank">' + url + "</a>";
    });
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    node.innerHTML = escaped.replace(/\n/g, "<br>");
  }

  function formatNumber(value) {
    try {
      return new Intl.NumberFormat(LANG === "ar" ? "ar-EG" : LANG, { useGrouping: true })
        .format(value)
        .replace(/[٠-٩۰-۹]/g, function (digit) {
          return String("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹".indexOf(digit) % 10);
        });
    } catch (error) {
      return String(value);
    }
  }

  function refreshQuota() {
    fetch("/api/agent/quota", { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        if (!quotaLine || !data) return;
        if (!data.enabled) {
          quotaLine.textContent = t("ai.disabled");
          return;
        }
        if (typeof data.remaining === "number") {
          quotaLine.textContent = formatNumber(data.remaining) + " " + t("agent.quota_left_label");
        }
      })
      .catch(function () {
        /* quota display is best effort */
      });
  }

  function setPending(value) {
    pending = value;
    if (send) send.disabled = value;
    if (stopButton) stopButton.hidden = !value;
  }

  function handleEvent(event, data, bubble) {
    if (event === "session") {
      chatSession = (data && data.session) || chatSession;
      agent.dataset.session = chatSession;
      return;
    }
    if (event === "delta") {
      bubble.dataset.text = (bubble.dataset.text || "") + ((data && data.text) || "");
      renderInto(bubble, bubble.dataset.text);
      scrollLog();
      return;
    }
    if (event === "tool") {
      if (data && data.status === "done" && data.name) {
        var meta = bubble.querySelector(".agent-tools");
        if (!meta) {
          meta = doc.createElement("span");
          meta.className = "agent-tools";
          bubble.appendChild(meta);
        }
        var names = (meta.dataset.names || "").split(",").filter(Boolean);
        if (names.indexOf(data.name) === -1) names.push(data.name);
        meta.dataset.names = names.join(",");
        meta.textContent = t("agent.tools_used").replace("{tools}", names.join(", "));
      }
      return;
    }
    if (event === "ui") {
      if (data && data.ui_action === "apply_filters" && data.params) {
        var params = new URLSearchParams();
        Object.keys(data.params).forEach(function (key) {
          if (data.params[key] !== null && data.params[key] !== undefined && data.params[key] !== "") {
            params.set(key, data.params[key]);
          }
        });
        var link = doc.createElement("a");
        link.href = "/jobs?" + params.toString();
        link.textContent = t("common.show_more");
        link.className = "link";
        bubble.appendChild(doc.createElement("br"));
        bubble.appendChild(link);
        scrollLog();
      }
      return;
    }
    if (event === "quota") {
      bubble.classList.add("error");
      var quotaText = t("agent.quota_exhausted");
      if (data && data.reset_at) {
        try {
          quotaText = quotaText.replace("{when}", new Date(data.reset_at).toLocaleString());
        } catch (error) {
          /* ignore */
        }
      }
      renderInto(bubble, quotaText.replace("{when}", ""));
      setPending(false);
      return;
    }
    if (event === "error") {
      bubble.classList.add("error");
      renderInto(bubble, t("agent.error"));
      setPending(false);
      return;
    }
    if (event === "done") {
      setPending(false);
      if (!(bubble.dataset.text || "").trim()) {
        bubble.parentNode && bubble.parentNode.removeChild(bubble);
      }
      refreshQuota();
    }
  }

  function parseSseChunk(chunk, bubble) {
    var blocks = chunk.split("\n\n");
    blocks.forEach(function (block) {
      if (!block.trim()) return;
      var event = "message";
      var payload = "";
      block.split("\n").forEach(function (line) {
        if (line.indexOf("event:") === 0) event = line.slice(6).trim();
        else if (line.indexOf("data:") === 0) payload += line.slice(5).trim();
      });
      if (!payload) return;
      var parsed = null;
      try {
        parsed = JSON.parse(payload);
      } catch (error) {
        parsed = { text: payload };
      }
      handleEvent(event, parsed, bubble);
    });
  }

  function submitMessage() {
    if (!input || pending) return;
    var text = input.value.trim();
    if (!text) return;
    openPanel();
    addMessage("user", text);
    input.value = "";
    var bubble = addMessage("assistant", "");
    if (!bubble) return;
    bubble.dataset.text = "";
    var thinking = doc.createElement("span");
    thinking.className = "agent-thinking";
    thinking.textContent = t("agent.thinking");
    bubble.appendChild(thinking);
    setPending(true);

    ensureSession().then(function (session) {
      if (!session) {
        setPending(false);
        return;
      }
      controller = "AbortController" in window ? new AbortController() : null;
      fetch("/api/agent/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ message: text, session: session, csrf: csrf }),
        signal: controller ? controller.signal : undefined,
      })
        .then(function (response) {
          if (!response.ok || !response.body) throw new Error("stream failed");
          var reader = response.body.getReader();
          var decoder = new TextDecoder("utf-8");
          var buffer = "";
          function pump() {
            return reader.read().then(function (result) {
              if (result.done) {
                if (buffer.trim()) parseSseChunk(buffer, bubble);
                setPending(false);
                return;
              }
              buffer += decoder.decode(result.value, { stream: true });
              var split = buffer.lastIndexOf("\n\n");
              if (split !== -1) {
                parseSseChunk(buffer.slice(0, split + 2), bubble);
                buffer = buffer.slice(split + 2);
              }
              return pump();
            });
          }
          return pump();
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            bubble.classList.add("error");
            if (!(bubble.dataset.text || "").trim()) renderInto(bubble, t("agent.stop"));
          } else {
            bubble.classList.add("error");
            renderInto(bubble, t("agent.error"));
          }
          setPending(false);
        });
    });
  }

  on(launch, "click", function () {
    if (panel && panel.hidden) openPanel();
    else closePanel();
  });
  on(close, "click", closePanel);
  on(doc, "keydown", function (event) {
    if (event.key === "Escape" && panel && !panel.hidden) closePanel();
  });
  on(form, "submit", function (event) {
    event.preventDefault();
    submitMessage();
  });
  on(input, "keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitMessage();
    }
  });
  on(stopButton, "click", function () {
    if (controller) controller.abort();
  });
  on(clearButton, "click", function () {
    if (log) log.innerHTML = "";
    if (input) input.focus();
  });

  Array.prototype.forEach.call(doc.querySelectorAll("[data-agent-open]"), function (button) {
    on(button, "click", openPanel);
  });

  refreshQuota();
})();
