/* Shared behaviour for every page. */
(() => {
  const EJP = (window.EJP = window.EJP || {});

  const SAVED_KEY = "ejp_saved_v1";
  const PROFILE_KEY = "ejp_profile_v1";

  function read(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (err) {
      /* Private mode: keep the session usable without persistence. */
    }
  }

  const store = {
    saved() {
      const value = read(SAVED_KEY, {});
      return value && typeof value === "object" ? value : {};
    },
    saveAll(value) {
      write(SAVED_KEY, value);
    },
    profile() {
      const value = read(PROFILE_KEY, {});
      return value && typeof value === "object" ? value : {};
    },
    saveProfile(value) {
      write(PROFILE_KEY, value);
    },
    isSaved(id) {
      return Boolean(store.saved()[id]);
    },
    toggle(job) {
      const saved = store.saved();
      if (saved[job.id]) {
        delete saved[job.id];
      } else {
        saved[job.id] = job;
      }
      store.saveAll(saved);
      updateSavedCounts();
      return Boolean(saved[job.id]);
    },
    count() {
      return Object.keys(store.saved()).length;
    },
  };

  function escapeHTML(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function timeAgo(days) {
    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days} days ago`;
    if (days < 14) return "1 week ago";
    if (days < 21) return "2 weeks ago";
    return "3 weeks ago";
  }

  function money(value) {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 0,
    }).format(value);
  }

  function updateSavedCounts() {
    const count = store.count();
    document.querySelectorAll("[data-saved-count]").forEach((node) => {
      node.textContent = count;
      node.classList.toggle("has-items", count > 0);
      const savedLink = node.closest(".nav-icon");
      if (savedLink) savedLink.setAttribute("aria-label", `Saved roles, ${count} saved`);
    });
  }

  let toastTimer = null;
  function toast(message) {
    let node = document.querySelector(".toast");
    if (!node) {
      node = document.createElement("div");
      node.className = "toast";
      node.setAttribute("role", "status");
      node.setAttribute("aria-live", "polite");
      document.body.appendChild(node);
    }
    node.textContent = message;
    requestAnimationFrame(() => node.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("show"), 2400);
  }

  function initNav() {
    const toggle = document.querySelector(".nav-toggle");
    const menu = document.querySelector(".mobile-menu");
    if (toggle && menu) {
      const setMenuOpen = (open, restoreFocus) => {
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
        menu.classList.toggle("open", open);
        if (!open && restoreFocus) toggle.focus();
      };

      toggle.addEventListener("click", () => {
        setMenuOpen(toggle.getAttribute("aria-expanded") !== "true");
      });

      menu.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => setMenuOpen(false));
      });

      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || toggle.getAttribute("aria-expanded") !== "true") return;
        event.preventDefault();
        setMenuOpen(false, true);
      });

      document.addEventListener("click", (event) => {
        if (toggle.getAttribute("aria-expanded") !== "true") return;
        if (menu.contains(event.target) || toggle.contains(event.target)) return;
        setMenuOpen(false);
      });

      const desktop = window.matchMedia("(min-width: 821px)");
      const closeOnDesktop = (event) => {
        if (event.matches) setMenuOpen(false);
      };
      if (desktop.addEventListener) desktop.addEventListener("change", closeOnDesktop);
      else desktop.addListener(closeOnDesktop);
    }

    const path = window.location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav-links a, .mobile-menu a").forEach((link) => {
      const href = (link.getAttribute("href") || "").split("#")[0].split("?")[0];
      if (href === path) link.setAttribute("aria-current", "page");
    });
  }

  function initReveal() {
    const nodes = document.querySelectorAll(".reveal");
    if (!nodes.length) return;
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      nodes.forEach((node) => node.classList.add("in"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    nodes.forEach((node) => observer.observe(node));
  }

  function init() {
    updateSavedCounts();
    initNav();
    initReveal();
    document.querySelectorAll("[data-year]").forEach((node) => {
      node.textContent = new Date().getFullYear();
    });
  }

  EJP.store = store;
  EJP.escapeHTML = escapeHTML;
  EJP.timeAgo = timeAgo;
  EJP.money = money;
  EJP.toast = toast;
  EJP.updateSavedCounts = updateSavedCounts;
  EJP.country = (code) => EJP.COUNTRY_META[code] || { name: code, flag: "🌍", route: "Visa route", portal: "Official portal", portalUrl: "#" };
  EJP.countryList = () =>
    Object.entries(EJP.COUNTRY_META || {})
      .map(([code, meta]) => ({ code, ...meta }))
      .sort((a, b) => a.name.localeCompare(b.name));
  EJP.roleLabel = (id) => (EJP.ROLES.find((role) => role.id === id) || { label: "All roles" }).label;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
