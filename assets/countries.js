/* Country directory: search + region filtering. */
(() => {
  const { PORTALS, REGIONS } = EJP;
  const esc = EJP.escapeHTML;
  const $ = (selector, root = document) => root.querySelector(selector);

  const grid = $("#portal-grid");
  const meta = $("#portal-meta");
  const tabs = $("#region-tabs");
  const form = $("#portal-search-form");
  const search = $("#portal-search");

  const params = new URLSearchParams(window.location.search);
  const state = {
    q: (params.get("q") || "").trim(),
    region: params.get("region") || "all",
  };
  if (!REGIONS.some((region) => region.id === state.region)) state.region = "all";

  const regionName = (id) => {
    if (id === "pan") return "Pan-European";
    return (REGIONS.find((region) => region.id === id) || { label: "Europe" }).label;
  };

  function countFor(regionId) {
    return regionId === "all" ? PORTALS.length : PORTALS.filter((portal) => portal.region === regionId).length;
  }

  let tabsBuilt = false;

  function buildTabs() {
    if (!tabsBuilt) {
      tabs.innerHTML = REGIONS.map(
        (region) => `
          <button class="region-tab" type="button" data-region="${region.id}" aria-pressed="false">
            ${esc(region.label)} <span class="region-count">${countFor(region.id)}</span>
          </button>`
      ).join("");
      tabsBuilt = true;
    }

    tabs.querySelectorAll("[data-region]").forEach((button) => {
      const active = button.getAttribute("data-region") === state.region;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function syncURL() {
    const next = new URLSearchParams();
    if (state.q) next.set("q", state.q);
    if (state.region !== "all") next.set("region", state.region);
    const query = next.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : ""));
  }

  function matches(portal, tokens) {
    const haystack = [
      portal.name,
      portal.country,
      portal.type,
      portal.desc,
      portal.route,
      regionName(portal.region),
    ]
      .join(" ")
      .toLowerCase();
    return tokens.every((token) => haystack.includes(token));
  }

  function render() {
    const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    const list = PORTALS.filter((portal) => {
      if (state.region !== "all" && portal.region !== state.region) return false;
      return matches(portal, tokens);
    });

    buildTabs();
    search.value = state.q;

    if (!list.length) {
      grid.innerHTML = `
        <div class="portal-empty">
          <p style="font-size:18px;color:var(--ink);font-weight:600;margin-bottom:6px">No portals match “${esc(state.q)}”</p>
          <p style="margin-bottom:20px">Try a country name, a region, or a portal.</p>
          <button class="btn btn-dark btn-sm" type="button" id="portal-reset">Clear search</button>
        </div>`;
      meta.textContent = "0 portals";
      const reset = $("#portal-reset");
      if (reset) {
        reset.addEventListener("click", () => {
          state.q = "";
          state.region = "all";
          render();
          syncURL();
        });
      }
      return;
    }

    grid.innerHTML = list
      .map(
        (portal) => `
        <a class="portal-card" href="${esc(portal.url)}" target="_blank" rel="noopener noreferrer">
          <div class="portal-top">
            <span class="portal-flag" aria-hidden="true">${portal.flag}</span>
            <span class="portal-region">${esc(regionName(portal.region))}</span>
          </div>
          <div>
            <h3>${esc(portal.name)}</h3>
            <p class="portal-type">${esc(portal.type)}</p>
          </div>
          <p class="portal-desc">${esc(portal.desc)}</p>
          <span class="portal-route">${esc(portal.route)}</span>
          <span class="link link-arrow">Visit official portal</span>
        </a>`
      )
      .join("");

    const regionText = state.region === "all" ? "all regions" : regionName(state.region);
    const searchText = state.q ? ` · “${state.q}”` : "";
    meta.textContent = `${list.length} of ${PORTALS.length} portals · ${regionText}${searchText}`;
  }

  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-region]");
    if (!button) return;
    state.region = button.getAttribute("data-region");
    render();
    syncURL();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.q = search.value.trim();
    render();
    syncURL();
  });

  let timer = null;
  search.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      state.q = search.value.trim();
      render();
      syncURL();
    }, 160);
  });

  render();
})();
