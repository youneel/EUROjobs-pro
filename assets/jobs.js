/* Jobs page: search, filters, saved roles and the detail drawer. */
(() => {
  const { JOBS, ROLES } = EJP;
  const esc = EJP.escapeHTML;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const grid = $("#job-grid");
  const searchForm = $("#search-form");
  const searchInput = $("#job-search");
  const countrySelect = $("#filter-country");
  const roleSelect = $("#filter-role");
  const sortSelect = $("#filter-sort");
  const visaToggle = $("#filter-visa");
  const savedToggle = $("#filter-saved");
  const toolbarCount = $("#toolbar-count");
  const resultsTitle = $("#results-title");
  const resultsMeta = $("#results-meta");

  const overlay = $("#overlay");
  const drawer = $("#drawer");
  const drawerTitle = $("#drawer-title");
  const drawerKicker = $("#drawer-kicker");
  const drawerCompany = $("#drawer-company");
  const drawerBody = $("#drawer-body");
  const drawerApply = $("#drawer-apply");
  const drawerSave = $("#drawer-save");
  const drawerClose = $("#drawer-close");

  const params = new URLSearchParams(window.location.search);
  const state = {
    q: (params.get("q") || "").trim(),
    country: params.get("country") || "all",
    role: params.get("role") || "all",
    visa: params.get("visa") === "1",
    savedOnly: params.get("saved") === "1",
    sort: params.get("sort") || "relevance",
  };

  let currentJob = null;
  let lastFocused = null;

  const heart = `
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
      <path d="M12 20.5s-7.5-4.7-7.5-10A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 7.5 3.5c0 5.3-7.5 10-7.5 10Z"/>
    </svg>`;

  /* ---------------------------------------------------------------- filters */

  function jobCountries() {
    const seen = new Set(JOBS.map((job) => job.country));
    return Array.from(seen)
      .map((code) => ({ code, ...EJP.country(code) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  function buildFilters() {
    jobCountries().forEach((country) => {
      const option = document.createElement("option");
      option.value = country.code;
      option.textContent = `${country.name} (${JOBS.filter((job) => job.country === country.code).length})`;
      countrySelect.appendChild(option);
    });

    ROLES.forEach((role) => {
      const option = document.createElement("option");
      option.value = role.id;
      option.textContent = role.label;
      roleSelect.appendChild(option);
    });

    // Accept a country name as well as a code in the URL.
    if (!EJP.COUNTRY_META[state.country]) {
      const byName = jobCountries().find(
        (country) => country.name.toLowerCase() === String(state.country).toLowerCase()
      );
      state.country = byName ? byName.code : "all";
    }
    if (!ROLES.some((role) => role.id === state.role)) state.role = "all";
    if (!["relevance", "newest", "salary", "company"].includes(state.sort)) state.sort = "relevance";

    searchInput.value = state.q;
    countrySelect.value = state.country;
    roleSelect.value = state.role;
    sortSelect.value = state.sort;
    visaToggle.setAttribute("aria-pressed", String(state.visa));
    savedToggle.setAttribute("aria-pressed", String(state.savedOnly));
  }

  function syncURL() {
    const next = new URLSearchParams();
    if (state.q) next.set("q", state.q);
    if (state.country !== "all") next.set("country", state.country);
    if (state.role !== "all") next.set("role", state.role);
    if (state.visa) next.set("visa", "1");
    if (state.savedOnly) next.set("saved", "1");
    if (state.sort !== "relevance") next.set("sort", state.sort);
    const query = next.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : ""));
  }

  function filteredJobs() {
    const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean);

    let list = JOBS.filter((job) => {
      const country = EJP.country(job.country);
      const role = EJP.roleLabel(job.role);
      const haystack = `${job.title} ${job.company} ${job.city} ${country.name} ${role}`.toLowerCase();

      if (!tokens.every((token) => haystack.includes(token))) return false;
      if (state.country !== "all" && job.country !== state.country) return false;
      if (state.role !== "all" && job.role !== state.role) return false;
      if (state.visa && !job.visa) return false;
      if (state.savedOnly && !EJP.store.isSaved(job.id)) return false;
      return true;
    });

    if (state.sort === "newest") {
      list = list.sort((a, b) => a.postedDays - b.postedDays);
    } else if (state.sort === "salary") {
      list = list.sort((a, b) => b.salaryValue - a.salaryValue);
    } else if (state.sort === "company") {
      list = list.sort((a, b) => a.company.localeCompare(b.company));
    } else {
      list = list.sort(
        (a, b) => Number(Boolean(b.featured)) - Number(Boolean(a.featured)) || a.postedDays - b.postedDays
      );
    }
    return list;
  }

  /* ------------------------------------------------------------------ cards */

  function chipsFor(job) {
    const chips = [];
    if (job.visa) chips.push('<span class="chip green">Visa supported</span>');
    if (job.blueCard) chips.push('<span class="chip blue">Blue Card</span>');
    if (job.relocation) chips.push('<span class="chip">Relocation</span>');
    if (job.remote === "Hybrid") chips.push('<span class="chip">Hybrid</span>');
    if (!chips.length) chips.push(`<span class="chip">${esc(job.type)}</span>`);
    return chips.slice(0, 3).join("");
  }

  function cardHTML(job) {
    const country = EJP.country(job.country);
    const saved = EJP.store.isSaved(job.id);
    const posted = job.postedDays === 0 ? "Posted today" : `Posted ${EJP.timeAgo(job.postedDays)}`;

    return `
      <article class="job-card" data-id="${esc(job.id)}">
        <div class="job-top">
          <span class="job-logo" style="--tone:${esc(job.tone)}" aria-hidden="true"><span>${esc(job.logo)}</span></span>
          <button class="save-btn" type="button" data-save="${esc(job.id)}"
            aria-pressed="${saved}" aria-label="${saved ? "Remove" : "Save"} ${esc(job.title)} ${saved ? "from" : "to"} saved roles">
            ${heart}
          </button>
        </div>
        <div class="job-body">
          <p class="job-company">${esc(job.company)} · ${esc(job.city)}, ${esc(country.name)}</p>
          <h3><button class="job-open" type="button" data-open="${esc(job.id)}">${esc(job.title)}</button></h3>
          <p class="job-salary">${esc(job.salary)} <span>gross / year</span></p>
          <div class="job-chips">${chipsFor(job)}</div>
        </div>
        <div class="job-foot">
          <span>${posted} · ${esc(job.type)}</span>
          <span class="arrow" aria-hidden="true">→</span>
        </div>
      </article>`;
  }

  function emptyHTML() {
    if (state.savedOnly && EJP.store.count() === 0) {
      return `
        <div class="empty-state">
          <span class="empty-icon">${heart}</span>
          <h3>No saved roles yet</h3>
          <p>Tap the heart on a role that catches your eye. It will wait for you here — quietly, on this device.</p>
          <button class="btn btn-dark" type="button" data-reset>Browse all roles</button>
        </div>`;
    }
    return `
      <div class="empty-state">
        <span class="empty-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="m20 20-3.4-3.4"/>
          </svg>
        </span>
        <h3>No roles match those filters</h3>
        <p>Try a broader search, another country, or clear the filters to see everything.</p>
        <button class="btn btn-dark" type="button" data-reset>Clear filters</button>
      </div>`;
  }

  function render() {
    const jobs = filteredJobs();

    grid.innerHTML = jobs.length ? jobs.map(cardHTML).join("") : emptyHTML();

    resultsTitle.textContent = state.savedOnly ? "Saved roles" : "Open roles";
    toolbarCount.textContent = `${jobs.length} ${jobs.length === 1 ? "role" : "roles"}`;

    const context = [];
    if (state.country !== "all") context.push(EJP.country(state.country).name);
    if (state.role !== "all") context.push(EJP.roleLabel(state.role));
    if (state.visa) context.push("visa supported");
    if (state.q) context.push(`“${state.q}”`);

    resultsMeta.textContent = jobs.length
      ? `Showing ${jobs.length} of ${JOBS.length} roles${context.length ? ` · ${context.join(" · ")}` : " across Europe"}`
      : `0 roles${context.length ? ` · ${context.join(" · ")}` : ""}`;

    EJP.updateSavedCounts();
    if (currentJob) {
      const saved = EJP.store.isSaved(currentJob.id);
      drawerSave.setAttribute("aria-pressed", String(saved));
      drawerSave.setAttribute("aria-label", saved ? "Remove role from saved" : "Save role");
    }
  }

  /* ----------------------------------------------------------------- drawer */

  function drawerHTML(job) {
    const country = EJP.country(job.country);
    const role = EJP.ROLE_META[job.role];
    const posted = job.postedDays === 0 ? "Today" : EJP.timeAgo(job.postedDays);
    const letterParams = new URLSearchParams({
      role: job.title,
      company: job.company,
      country: job.country,
      city: job.city,
    });

    return `
      <div class="drawer-meta">
        <div><span>Salary</span><strong>${esc(job.salary)}</strong></div>
        <div><span>Location</span><strong>${esc(job.city)}, ${esc(country.name)}</strong></div>
        <div><span>Work style</span><strong>${esc(job.remote)}</strong></div>
        <div><span>Posted</span><strong>${esc(posted)}</strong></div>
      </div>

      <div class="drawer-section" style="border-top:0;margin-top:0;padding-top:0">
        <h3>About the role</h3>
        <p>${esc(job.blurb)}</p>
      </div>

      <div class="drawer-section">
        <h3>What you'll do</h3>
        <ul>${role.duties.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </div>

      <div class="drawer-section">
        <h3>What we're looking for</h3>
        <ul>${role.requirements.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </div>

      <div class="drawer-section">
        <h3>What's included</h3>
        <ul>${role.benefits.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </div>

      <div class="visa-box">
        <div class="visa-route"><span class="flag">${country.flag}</span>${esc(country.route)}</div>
        <p>${esc(country.note)}</p>
        <span class="visa-note">
          ${job.visa ? "This demo role is marked as visa-supporting." : "Visa support is not stated for this role."}
          General information only — confirm with the official authority.
        </span>
      </div>

      <div class="drawer-section">
        <h3>How to apply</h3>
        <p>
          Applications are handled by <strong>${esc(country.portal)}</strong>, the official public
          employment service for ${esc(country.name)}. The button below opens their site in a new tab.
          EuroJobs Pro never charges candidates and never asks for payment details.
        </p>
        <p style="margin-top:12px">
          <a class="link link-arrow" href="tools.html?${letterParams.toString()}#letter">Draft a cover letter for this role</a>
        </p>
      </div>`;
  }

  function openDrawer(id) {
    const job = JOBS.find((item) => item.id === id) || EJP.store.saved()[id];
    if (!job) return;

    currentJob = job;
    lastFocused = document.activeElement;

    const country = EJP.country(job.country);
    drawerKicker.textContent = `${EJP.roleLabel(job.role)} · ${job.type}`;
    drawerTitle.textContent = job.title;
    drawerCompany.textContent = `${job.company} · ${job.city}, ${country.name}`;
    drawerBody.innerHTML = drawerHTML(job);

    drawerApply.href = country.portalUrl;
    drawerApply.setAttribute("aria-label", `Open the ${country.portal} portal in a new tab`);

    const saved = EJP.store.isSaved(job.id);
    drawerSave.setAttribute("aria-pressed", String(saved));
    drawerSave.setAttribute("aria-label", saved ? "Remove role from saved" : "Save role");

    drawer.removeAttribute("inert");
    drawer.setAttribute("aria-hidden", "false");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("no-scroll");

    requestAnimationFrame(() => {
      overlay.classList.add("open");
      drawer.classList.add("open");
    });

    window.setTimeout(() => drawerClose.focus({ preventScroll: true }), 60);
  }

  function closeDrawer() {
    if (!drawer.classList.contains("open")) return;
    overlay.classList.remove("open");
    drawer.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    drawer.setAttribute("aria-hidden", "true");
    drawer.setAttribute("inert", "");
    document.body.classList.remove("no-scroll");

    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus({ preventScroll: true });
    }
  }

  function toggleSave(id) {
    const job = JOBS.find((item) => item.id === id) || EJP.store.saved()[id];
    if (!job) return;
    const saved = EJP.store.toggle(job);
    EJP.toast(saved ? "Saved to your roles" : "Removed from saved roles");
    syncSaveButtons(id, saved);

    if (state.savedOnly) render();

    if (currentJob && currentJob.id === id) {
      drawerSave.setAttribute("aria-pressed", String(saved));
      drawerSave.setAttribute("aria-label", saved ? "Remove role from saved" : "Save role");
    }
  }

  function syncSaveButtons(id, saved) {
    $$(`[data-save="${CSS.escape(id)}"]`).forEach((button) => {
      button.setAttribute("aria-pressed", String(saved));
      const title = JOBS.find((job) => job.id === id)?.title || "role";
      button.setAttribute(
        "aria-label",
        `${saved ? "Remove" : "Save"} ${title} ${saved ? "from" : "to"} saved roles`
      );
    });
  }

  /* ---------------------------------------------------------------- events */

  grid.addEventListener("click", (event) => {
    const saveButton = event.target.closest("[data-save]");
    if (saveButton) {
      event.preventDefault();
      toggleSave(saveButton.getAttribute("data-save"));
      return;
    }

    const reset = event.target.closest("[data-reset]");
    if (reset) {
      state.q = "";
      state.country = "all";
      state.role = "all";
      state.visa = false;
      state.savedOnly = false;
      searchInput.value = "";
      countrySelect.value = "all";
      roleSelect.value = "all";
      visaToggle.setAttribute("aria-pressed", "false");
      savedToggle.setAttribute("aria-pressed", "false");
      render();
      syncURL();
      return;
    }

    const card = event.target.closest(".job-card");
    if (card) openDrawer(card.getAttribute("data-id"));
  });

  grid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".job-card");
    if (card && !event.target.closest("button")) {
      event.preventDefault();
      openDrawer(card.getAttribute("data-id"));
    }
  });

  drawerSave.addEventListener("click", () => {
    if (currentJob) toggleSave(currentJob.id);
  });

  drawerClose.addEventListener("click", closeDrawer);
  overlay.addEventListener("click", closeDrawer);

  document.addEventListener("keydown", (event) => {
    if (!drawer.classList.contains("open")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDrawer();
      return;
    }
    if (event.key === "Tab") {
      const focusable = $$(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        drawer
      ).filter((node) => node.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    state.q = searchInput.value.trim();
    render();
    syncURL();
  });

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.q = searchInput.value.trim();
      render();
      syncURL();
    }, 160);
  });

  countrySelect.addEventListener("change", () => {
    state.country = countrySelect.value;
    render();
    syncURL();
  });

  roleSelect.addEventListener("change", () => {
    state.role = roleSelect.value;
    render();
    syncURL();
  });

  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    render();
    syncURL();
  });

  visaToggle.addEventListener("click", () => {
    state.visa = !state.visa;
    visaToggle.setAttribute("aria-pressed", String(state.visa));
    render();
    syncURL();
  });

  savedToggle.addEventListener("click", () => {
    state.savedOnly = !state.savedOnly;
    savedToggle.setAttribute("aria-pressed", String(state.savedOnly));
    render();
    syncURL();
  });

  $$("[data-quick-role]").forEach((button) => {
    button.addEventListener("click", () => {
      state.role = button.getAttribute("data-quick-role");
      state.savedOnly = false;
      roleSelect.value = state.role;
      savedToggle.setAttribute("aria-pressed", "false");
      render();
      syncURL();
    });
  });

  $$("[data-quick-visa]").forEach((button) => {
    button.addEventListener("click", () => {
      state.visa = true;
      visaToggle.setAttribute("aria-pressed", "true");
      render();
      syncURL();
    });
  });

  buildFilters();
  render();
})();
