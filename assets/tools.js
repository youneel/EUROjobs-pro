/* Toolkit: CV profile, cover-letter generator and local visa advisor. */
(() => {
  const esc = EJP.escapeHTML;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const params = new URLSearchParams(window.location.search);

  const profileFields = ["name", "headline", "email", "phone", "location", "years", "skills", "languages", "summary"];

  /* ------------------------------------------------------------------ tabs */

  const tabs = $$(".tool-tab");
  const panels = $$(".tool-panel");
  const validTools = ["cv", "letter", "advisor"];

  function activateTool(tool, options) {
    const opts = options || {};
    if (!validTools.includes(tool)) tool = "cv";

    tabs.forEach((tab) => {
      const active = tab.getAttribute("data-tool") === tool;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });

    panels.forEach((panel) => {
      const active = panel.getAttribute("data-tool-panel") === tool;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });

    if (opts.updateHash !== false) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${tool}`);
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTool(tab.getAttribute("data-tool")));
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next === null) return;
      event.preventDefault();
      const target = tabs[next];
      activateTool(target.getAttribute("data-tool"));
      target.focus();
    });
  });

  $$("[data-goto]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      activateTool(link.getAttribute("data-goto"));
      $(".tool-tabs").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  window.addEventListener("hashchange", () => {
    const hash = window.location.hash.replace("#", "");
    if (!validTools.includes(hash)) return;
    activateTool(hash, { updateHash: false });
    const tabBar = $(".tool-tabs");
    if (tabBar) {
      tabBar.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    }
  });

  /* -------------------------------------------------------------- CV studio */

  const cvForm = $("#cv-form");
  const cvStatus = $("#cv-status");
  const dropzone = $("#dropzone");
  const fileInput = $("#cv-file");

  const KNOWN_SKILLS = [
    { label: "JavaScript", terms: ["javascript"] },
    { label: "TypeScript", terms: ["typescript"] },
    { label: "React", terms: ["react", "react.js", "reactjs"] },
    { label: "Next.js", terms: ["next.js", "nextjs", "next js"] },
    { label: "Node.js", terms: ["node.js", "nodejs", "node js", "node"] },
    { label: "Python", terms: ["python"] },
    { label: "Java", terms: ["java"] },
    { label: "C#", terms: ["c#", "c sharp"] },
    { label: ".NET", terms: [".net", "dotnet", "asp.net"] },
    { label: "SQL", terms: ["sql"] },
    { label: "PostgreSQL", terms: ["postgresql", "postgres"] },
    { label: "Kubernetes", terms: ["kubernetes", "k8s"] },
    { label: "Docker", terms: ["docker"] },
    { label: "AWS", terms: ["aws", "amazon web services"] },
    { label: "Azure", terms: ["azure"] },
    { label: "GCP", terms: ["gcp", "google cloud"] },
    { label: "Figma", terms: ["figma"] },
    { label: "UX", terms: ["ux", "user experience"] },
    { label: "UI", terms: ["ui", "user interface"] },
    { label: "HTML", terms: ["html"] },
    { label: "CSS", terms: ["css"] },
    { label: "Git", terms: ["git"] },
    { label: "dbt", terms: ["dbt"] },
    { label: "Spark", terms: ["spark", "apache spark"] },
    { label: "Nursing", terms: ["nursing"] },
    { label: "Patient care", terms: ["patient care"] },
    { label: "HGV", terms: ["hgv", "lgv"] },
    { label: "Forklift", terms: ["forklift"] },
    { label: "CNC", terms: ["cnc"] },
    { label: "Welding", terms: ["welding"] },
    { label: "Accounting", terms: ["accounting"] },
    { label: "Payroll", terms: ["payroll"] },
    { label: "Recruitment", terms: ["recruitment"] },
    { label: "Sales", terms: ["sales"] },
    { label: "Marketing", terms: ["marketing"] },
    { label: "Project management", terms: ["project management"] },
    { label: "Excel", terms: ["excel"] },
    { label: "Customer service", terms: ["customer service"] },
    { label: "Hospitality", terms: ["hospitality"] },
    { label: "Teaching", terms: ["teaching"] },
    { label: "Physiotherapy", terms: ["physiotherapy"] },
    { label: "DevOps", terms: ["devops"] },
    { label: "Cybersecurity", terms: ["cybersecurity", "cyber security"] },
  ];

  const KNOWN_LANGUAGES = [
    "English", "German", "French", "Spanish", "Dutch", "Italian", "Portuguese", "Polish",
    "Swedish", "Danish", "Norwegian", "Finnish", "Czech", "Romanian", "Lithuanian", "Estonian",
  ];

  function setStatus(message, kind) {
    cvStatus.textContent = message;
    cvStatus.className = "status-text" + (kind ? ` ${kind}` : "");
  }

  function setField(name, value) {
    if (value == null || value === "") return;
    const field = document.getElementById(`cv-${name}`);
    if (!field) return;
    field.value = value;
  }

  function profileFromForm() {
    const profile = {};
    profileFields.forEach((field) => {
      const node = document.getElementById(`cv-${field}`);
      if (node) profile[field] = node.value.trim();
    });
    return profile;
  }

  function fillForm(profile) {
    profileFields.forEach((field) => {
      const node = document.getElementById(`cv-${field}`);
      if (node && profile[field] != null) node.value = profile[field];
    });
  }

  function updateProfilePreview() {
    const profile = profileFromForm();
    const name = $("#pc-name");
    const role = $("#pc-role");
    const meta = $("#pc-meta");

    name.textContent = profile.name || "Your name";
    role.textContent = profile.headline || "Your headline";

    const chips = [];
    if (profile.location) chips.push(profile.location);
    if (profile.years) chips.push(`${profile.years} yrs experience`);
    profile.skills
      .split(",")
      .map((skill) => skill.trim())
      .filter(Boolean)
      .slice(0, 2)
      .forEach((skill) => chips.push(skill));

    meta.innerHTML = chips.length
      ? chips.map((chip) => `<span class="pc-chip">${esc(chip)}</span>`).join("")
      : '<span class="pc-chip">Add skills</span>';

    const checks = {
      identity: Boolean(profile.name && profile.headline),
      contact: Boolean(profile.email || profile.phone),
      location: Boolean(profile.location),
      skills: Boolean(profile.skills),
      summary: Boolean(profile.summary && profile.summary.length > 20),
    };

    let done = 0;
    Object.entries(checks).forEach(([key, ok]) => {
      if (ok) done += 1;
      const row = $(`[data-check="${key}"]`);
      if (row) row.classList.toggle("done", ok);
    });

    const pct = Math.round((done / Object.keys(checks).length) * 100);
    $("#cv-pct").textContent = `${pct}%`;
    $("#cv-meter").style.width = `${pct}%`;
  }

  let autoSaveTimer = null;
  function autoSaveProfile() {
    window.clearTimeout(autoSaveTimer);
    autoSaveTimer = window.setTimeout(() => {
      EJP.store.saveProfile(profileFromForm());
    }, 500);
  }

  cvForm.addEventListener("input", () => {
    updateProfilePreview();
    autoSaveProfile();
  });

  $("#cv-save").addEventListener("click", () => {
    EJP.store.saveProfile(profileFromForm());
    EJP.toast("Profile saved on this device");
    setStatus("Profile saved locally. Only you can see it.", "ok");
  });

  $("#cv-clear").addEventListener("click", () => {
    const hasContent = Object.values(profileFromForm()).some(Boolean);
    if (hasContent && !window.confirm("Clear your local profile? This cannot be undone.")) return;
    cvForm.reset();
    EJP.store.saveProfile({});
    updateProfilePreview();
    setStatus("Profile cleared.", "");
  });

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function findTermIndex(text, term) {
    const pattern = new RegExp(`(^|[^a-z0-9])${escapeRegExp(term)}(?![a-z0-9])`, "i");
    const match = pattern.exec(text);
    return match ? match.index + match[1].length : -1;
  }

  function applyParsedText(text) {
    const normalized = text.replace(/\r/g, "\n");
    const lines = normalized
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);

    const email = normalized.match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i);
    if (email) setField("email", email[0]);

    const phone = normalized.match(/(\+?\d[\d\s().-]{7,}\d)/);
    if (phone) {
      const candidate = phone[0].trim();
      if (candidate.replace(/\D/g, "").length >= 8) setField("phone", candidate);
    }

    const nameLine = lines.find(
      (line, index) =>
        index < 4 &&
        line.length <= 60 &&
        line.split(/\s+/).length <= 5 &&
        !/@|https?:|\d{3}/.test(line)
    );
    if (nameLine) setField("name", nameLine.replace(/\s+/g, " "));

    const roleWords = /engineer|developer|designer|nurse|manager|accountant|driver|technician|teacher|welder|chef|analyst|consultant|specialist|architect|coordinator/i;
    const headline = lines.find((line) => line.length <= 90 && roleWords.test(line) && line !== nameLine);
    if (headline) setField("headline", headline);

    const countryNames = EJP.countryList().map((country) => country.name);
    const location = lines.find(
      (line) => line.length <= 70 && countryNames.some((country) => line.toLowerCase().includes(country.toLowerCase()))
    );
    if (location) setField("location", location);

    const years = normalized.match(/(\d{1,2})\+?\s*(?:years|yrs)/i);
    if (years) setField("years", years[1]);

    const foundSkills = KNOWN_SKILLS.map((skill) => {
      const positions = skill.terms
        .map((term) => findTermIndex(normalized, term))
        .filter((position) => position >= 0);
      return positions.length ? { label: skill.label, at: Math.min(...positions) } : null;
    })
      .filter(Boolean)
      .sort((a, b) => a.at - b.at)
      .map((skill) => skill.label);
    if (foundSkills.length) setField("skills", foundSkills.slice(0, 8).join(", "));

    const foundLanguages = KNOWN_LANGUAGES.filter((language) => findTermIndex(normalized, language) >= 0);
    if (foundLanguages.length) setField("languages", foundLanguages.join(", "));

    const summary = lines.slice(0, 8).join(" ").replace(/\s+/g, " ").slice(0, 420);
    if (summary.length > 40) setField("summary", summary);

    updateProfilePreview();
    EJP.store.saveProfile(profileFromForm());
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error("script"));
      document.head.appendChild(script);
    });
  }

  async function readPDF(file) {
    const base = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
    await loadScript(`${base}pdf.min.js`);
    if (!window.pdfjsLib) throw new Error("pdf");
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${base}pdf.worker.min.js`;

    const buffer = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: buffer }).promise;
    let text = "";
    const pages = Math.min(pdf.numPages, 8);
    for (let pageNumber = 1; pageNumber <= pages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const content = await page.getTextContent();
      text += content.items.map((item) => item.str).join(" ") + "\n";
    }
    return text;
  }

  async function handleFile(file) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setStatus("That file is larger than 5 MB. Try a smaller export.", "error");
      return;
    }

    setStatus(`Reading ${file.name}…`);
    try {
      let text = "";
      if (/\.pdf$/i.test(file.name) || file.type === "application/pdf") {
        text = await readPDF(file);
      } else if (/\.(txt|md|markdown)$/i.test(file.name) || file.type.startsWith("text/")) {
        text = await file.text();
      } else {
        throw new Error("type");
      }

      if (!text || text.trim().length < 20) {
        setStatus("We couldn't find readable text in that file. Try a TXT export or type it in.", "error");
        return;
      }

      applyParsedText(text);
      setStatus(`Parsed ${file.name}. Review the fields below, then save.`, "ok");
    } catch (err) {
      if (err && err.message === "type") {
        setStatus("Unsupported file type. Use PDF, TXT or Markdown.", "error");
      } else if (/\.pdf$/i.test(file.name)) {
        setStatus("PDF reading isn't available right now (it needs a one-time download). Paste the text or use a TXT file.", "error");
      } else {
        setStatus("We couldn't read that file. Paste the text or use a TXT file.", "error");
      }
    } finally {
      fileInput.value = "";
    }
  }

  fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

  ["dragenter", "dragover"].forEach((type) => {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((type) => {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    handleFile(file);
  });

  /* ---------------------------------------------------------- cover letter */

  const countrySelect = $("#lt-country");
  EJP.countryList().forEach((country) => {
    const option = document.createElement("option");
    option.value = country.code;
    option.textContent = `${country.flag} ${country.name}`;
    countrySelect.appendChild(option);
  });

  const requestedCountry = (params.get("country") || "").toUpperCase();
  countrySelect.value = EJP.COUNTRY_META[requestedCountry] ? requestedCountry : "DE";
  const FALLBACK_ROLE = "Product Designer";

  function letterValue(id) {
    return document.getElementById(id).value.trim();
  }

  function listSentence(items) {
    if (items.length === 1) return items[0];
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
  }

  function fillLetterFromProfile(overwrite) {
    const profile = EJP.store.profile();
    const map = [
      ["lt-name", profile.name],
      ["lt-email", profile.email],
      ["lt-phone", profile.phone],
      ["lt-role", profile.headline],
      ["lt-years", profile.years],
      ["lt-skills", profile.skills],
    ];
    map.forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (!node || value == null || value === "") return;
      if (overwrite || !node.value.trim()) node.value = value;
    });
  }

  function ensureRoleField() {
    const field = $("#lt-role");
    if (!field.value.trim()) field.value = FALLBACK_ROLE;
    return field.value.trim();
  }

  function buildLetter() {
    const name = letterValue("lt-name") || "Your Name";
    const email = letterValue("lt-email");
    const phone = letterValue("lt-phone");
    const role = letterValue("lt-role") || FALLBACK_ROLE;
    const company = letterValue("lt-company");
    const city = letterValue("lt-city") || EJP.country(countrySelect.value).name;
    const years = letterValue("lt-years");
    const highlight = letterValue("lt-highlight");
    const tone = $("#lt-tone").value;
    const country = EJP.country(countrySelect.value);

    const skills = letterValue("lt-skills")
      .split(",")
      .map((skill) => skill.trim())
      .filter(Boolean)
      .slice(0, 3);
    const skillsText = skills.length ? listSentence(skills) : "the work described in the role";

    const companyAt = company ? ` at ${company}` : "";
    const companyTo = company ? ` to ${company}` : "";

    let intro = "";
    if (tone === "formal") {
      const experience = years
        ? `Over the past ${years} years, my experience has centred on ${skillsText}. `
        : `My experience centres on ${skillsText}. `;
      intro = `I am writing to express my interest in the ${role} position${companyAt}. ${experience}${highlight}`;
    } else if (tone === "concise") {
      const experience = years
        ? `${years} years of experience, focused on ${skillsText}.`
        : `My background is focused on ${skillsText}.`;
      intro = `I'm applying for the ${role} role${companyAt}. ${experience}${highlight ? ` ${highlight}` : ""}`;
    } else {
      const experience = years
        ? `Over the past ${years} years, I have built my work around ${skillsText}. `
        : `I have built my work around ${skillsText}. `;
      intro = `I was glad to come across the ${role} opening${companyAt}. ${experience}${highlight}`;
    }

    const relocation =
      `The move to ${country.name} is a deliberate one. I have looked at the ${country.route} route, ` +
      `the language expectations, and what employers in ${city} tend to ask for. I am ready to provide ` +
      `the qualifications, translations and references required for the relevant work authorisation.`;

    const contribution =
      `What I would bring${companyTo} is a habit of clear communication, careful work, and genuine ` +
      `curiosity about how a team does things. I would welcome the chance to discuss where I could ` +
      `contribute first, and to answer any questions about my experience or relocation timeline.`;

    const closing = tone === "formal" ? "Yours sincerely," : tone === "concise" ? "Best regards," : "Warm regards,";
    const date = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
    const salutation = company ? `Dear Hiring Team at ${company},` : "Dear Hiring Team,";

    const paragraphs = [intro.trim(), relocation, contribution];
    const signOff = `${email || phone ? `${email || ""}${email && phone ? " · " : ""}${phone || ""}` : ""}`;

    return {
      name,
      email,
      phone,
      date,
      role,
      text: `${date}\n\n${salutation}\n\n${paragraphs.join("\n\n")}\n\nThank you for your time and consideration.\n\n${closing}\n${name}${signOff ? `\n${signOff}` : ""}`,
    };
  }

  function commitEditing() {
    const paper = $("#letter-paper");
    if (!paper.classList.contains("editing")) return;
    $("#letter-body").textContent = $("#letter-edit").value;
    paper.classList.remove("editing");
    $("#letter-edit-toggle").textContent = "Edit text";
  }

  function renderLetter() {
    ensureRoleField();
    const letter = buildLetter();
    const paper = $("#letter-paper");
    paper.classList.remove("editing");
    $("#letter-edit-toggle").textContent = "Edit text";
    $("#letter-body").textContent = letter.text;
    $("#letter-brand-name").textContent = letter.name;
    $("#letter-date").textContent = letter.date;

    const contact = [letter.email, letter.phone].filter(Boolean);
    $("#letter-contact").innerHTML = contact.length
      ? contact.map((item) => `<span>${esc(item)}</span>`).join("")
      : "<span>email · phone</span>";

    $("#letter-edit").value = letter.text;
  }

  // Deep links from the jobs drawer prefill the role context.
  fillLetterFromProfile(false);
  if (params.get("role")) $("#lt-role").value = params.get("role");
  if (params.get("company")) $("#lt-company").value = params.get("company");
  if (params.get("city")) $("#lt-city").value = params.get("city");
  renderLetter();

  $("#letter-generate").addEventListener("click", () => {
    const enteringEdit = $("#letter-paper").classList.contains("editing");
    if (enteringEdit) commitEditing();
    renderLetter();
    EJP.toast("Draft refreshed — make it sound like you");
  });

  $("#letter-profile").addEventListener("click", () => {
    fillLetterFromProfile(true);
    renderLetter();
    EJP.toast("Profile applied to your letter");
  });

  $("#letter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    renderLetter();
  });

  $("#letter-edit-toggle").addEventListener("click", () => {
    const paper = $("#letter-paper");
    const button = $("#letter-edit-toggle");
    if (paper.classList.contains("editing")) {
      commitEditing();
      return;
    }
    $("#letter-edit").value = $("#letter-body").textContent;
    paper.classList.add("editing");
    button.textContent = "Preview";
    $("#letter-edit").focus();
  });

  function currentLetterText() {
    const paper = $("#letter-paper");
    return paper.classList.contains("editing") ? $("#letter-edit").value : $("#letter-body").textContent;
  }

  $("#letter-copy").addEventListener("click", async () => {
    const text = currentLetterText().trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    EJP.toast("Letter copied to clipboard");
  });

  $("#letter-download").addEventListener("click", () => {
    const text = currentLetterText().trim();
    if (!text) return;
    const role = letterValue("lt-role") || "application";
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Cover letter - ${role.replace(/[^\w\s-]/g, "").trim() || "application"}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    EJP.toast("Letter downloaded");
  });

  $("#letter-print").addEventListener("click", () => {
    commitEditing();
    window.print();
  });

  window.addEventListener("beforeprint", commitEditing);

  /* --------------------------------------------------------------- advisor */

  const ADVISOR = [
    {
      keys: ["blue card", "bluecard", "eu blue card", "blauwe kaart", "blaue karte"],
      html: `
        <p><strong>The EU Blue Card</strong> is a work-and-residence permit for highly qualified non-EU professionals. It is issued by a national authority, not by the EU itself, so the details vary by country.</p>
        <ul>
          <li>A recognised higher qualification (or, in some countries, substantial equivalent experience).</li>
          <li>A job offer meeting the national salary threshold. That threshold is updated every year.</li>
          <li>Passport, health insurance and the usual application documents.</li>
        </ul>
        <p>Your employer often starts the process, then you may need an entry visa before collecting the residence card. After a period of legal residence, limited intra-EU mobility can apply — but it is not automatic.</p>
        <p><a href="https://eures.europa.eu/index_en" target="_blank" rel="noopener noreferrer">EURES — official EU mobility portal</a></p>
        <p>Check the specific salary threshold and shortage-occupation rules on the national immigration site before relying on this route.</p>`,
    },
    {
      keys: ["germany", "german", "berlin", "munich", "opportunity card", "chancenkarte", "anmeldung"],
      html: `
        <p><strong>Germany</strong> has two routes worth knowing:</p>
        <ul>
          <li><strong>EU Blue Card</strong> — for qualified roles above the annual salary threshold.</li>
          <li><strong>Opportunity Card (Chancenkarte)</strong> — a points-based job-search route for qualified people. It lets you look for work; it is not a work permit on its own.</li>
        </ul>
        <p>Recognition of your qualification matters, especially in regulated professions. German helps in most sectors; English is common in tech. The federal <em>Make it in Germany</em> portal explains both routes and links to the official job exchange.</p>
        <p><a href="https://www.make-it-in-germany.com/en/" target="_blank" rel="noopener noreferrer">Make it in Germany</a> · <a href="https://www.arbeitsagentur.de/jobsuche/" target="_blank" rel="noopener noreferrer">Bundesagentur für Arbeit</a></p>`,
    },
    {
      keys: ["netherlands", "dutch", "amsterdam", "highly skilled", "kennismigrant", "30% ruling", "recognised sponsor"],
      html: `
        <p><strong>The Netherlands</strong> mostly hires international professionals through the <strong>highly skilled migrant</strong> route. The employer must be a recognised sponsor with the IND, and the salary must meet an age-based threshold.</p>
        <ul>
          <li>The employer applies; you generally do not apply alone.</li>
          <li>The <strong>30% ruling</strong> is a tax facility with its own conditions — it is not automatic.</li>
          <li>Recent graduates may qualify for an orientation year.</li>
        </ul>
        <p>English is widely used at work, but customer-facing and public-sector roles often require Dutch. Start with the official immigration service and the public job portal.</p>
        <p><a href="https://ind.nl/en" target="_blank" rel="noopener noreferrer">IND — Dutch immigration</a> · <a href="https://www.werk.nl/werkzoekenden/vacatures/" target="_blank" rel="noopener noreferrer">Werk.nl</a></p>`,
    },
    {
      keys: ["ireland", "irish", "dublin", "critical skills", "employment permit"],
      html: `
        <p><strong>Ireland</strong> uses the <strong>Critical Skills Employment Permit</strong> for occupations on the Critical Skills list, and the General Employment Permit for other eligible roles.</p>
        <ul>
          <li>The employer usually applies for the permit; salary thresholds apply.</li>
          <li>Critical Skills permits offer a faster path to family reunification and, after the required period, Stamp 4.</li>
          <li>English is the working language, but regulated professions still need recognition.</li>
        </ul>
        <p>Check the current Critical Skills list before you build a plan around a job title — it changes.</p>
        <p><a href="https://www.irishimmigration.ie/" target="_blank" rel="noopener noreferrer">Irish Immigration</a> · <a href="https://jobsireland.ie/en-US/browse-jobs" target="_blank" rel="noopener noreferrer">JobsIreland</a></p>`,
    },
    {
      keys: ["austria", "austrian", "vienna", "red-white-red", "rot-weiß-rot"],
      html: `
        <p><strong>Austria's Red-White-Red Card</strong> is points-based and aimed at shortage occupations and qualified workers. Points consider qualification, experience, language, age and other criteria.</p>
        <ul>
          <li>The employer is part of the application and the job must meet the relevant criteria.</li>
          <li>German is often required outside international tech teams.</li>
          <li>The EU Blue Card is an alternative for high-salary roles.</li>
        </ul>
        <p>The official migration portal explains the points system; AMS lists the vacancies. Confirm the current shortage list before applying.</p>
        <p><a href="https://www.migration.gv.at/en/" target="_blank" rel="noopener noreferrer">Migration.gv.at</a> · <a href="https://jobs.ams.at/public/emps/" target="_blank" rel="noopener noreferrer">AMS jobs</a></p>`,
    },
    {
      keys: ["nordics", "sweden", "denmark", "norway", "finland", "stockholm", "copenhagen", "oslo", "helsinki", "positive list", "pay limit"],
      html: `
        <p><strong>The Nordics</strong> share a high-trust, high-cost labour market, but the routes differ:</p>
        <ul>
          <li><strong>Sweden</strong> — a written offer is the anchor; unions are consulted on pay and conditions.</li>
          <li><strong>Denmark</strong> — the Positive List covers shortage professions; the Pay Limit Scheme targets high salaries.</li>
          <li><strong>Norway</strong> — not in the EU; a skilled worker permit needs a concrete offer and relevant qualification.</li>
          <li><strong>Finland</strong> — specialist and seasonal permits, with a fast track for some growth sectors.</li>
        </ul>
        <p>Family rights and language expectations vary. Use each country's official portal and immigration service.</p>
        <p><a href="countries.html?region=nordic">Compare Nordic portals in the directory</a></p>`,
    },
    {
      keys: ["salary", "pay", "wage", "threshold", "cost of living", "tax", "net"],
      html: `
        <p><strong>Salary thresholds are moving targets.</strong> Blue Card and permit minimums are revised each year, and many European jobs are covered by collective agreements that set minimum pay by role and region.</p>
        <ul>
          <li>Compare gross annual pay, then look at tax and social contributions — net income varies a lot.</li>
          <li>Check whether relocation, housing, language courses and transport are included.</li>
          <li>Use official job portals and union or employer-association sources, not a single blog post.</li>
        </ul>
        <p>EURES publishes country-by-country labour market information and salary guidance. For a specific role, ask the employer for the collective agreement and the salary band in writing.</p>
        <p><a href="https://eures.europa.eu/index_en" target="_blank" rel="noopener noreferrer">EURES country information</a></p>`,
    },
    {
      keys: ["cv", "resume", "curriculum", "europass", "application document"],
      html: `
        <p><strong>A good European CV is clear before it is decorative.</strong> One to two pages, reverse chronological, with results rather than duties.</p>
        <ul>
          <li>Include language levels honestly (CEFR: A1–C2) and your work-authorisation status if relevant.</li>
          <li>Local norms differ: photos and personal details are expected in some markets and best left out in others.</li>
          <li>For regulated professions, list your registration or recognition status.</li>
          <li>Keep a PDF and a plain-text version — some portals parse only text.</li>
        </ul>
        <p>Europass is a recognised optional format, not a requirement. Tailor the top third of the CV to the role you are applying for.</p>
        <p><a href="https://europa.eu/europass/en" target="_blank" rel="noopener noreferrer">Europass</a> · <a href="tools.html#cv">Build your profile here</a></p>`,
    },
    {
      keys: ["language", "german", "french", "dutch", "spanish", "italian", "english", "cefr", "fluent", "b1", "b2"],
      html: `
        <p><strong>Language requirements depend on the job, not just the country.</strong> Tech and international teams often work in English; healthcare, teaching, driving, hospitality and public-facing roles usually need the local language.</p>
        <ul>
          <li>CEFR levels: A1–A2 beginner, B1–B2 independent, C1–C2 fluent/professional.</li>
          <li>Employers may accept a conversation-level interview instead of a certificate — ask.</li>
          <li>Free or subsidised courses are often available through integration programmes, employers and universities.</li>
        </ul>
        <p>Do not overstate your level on a CV. It is better to say “B1, improving” than to be tested in the first meeting.</p>`,
    },
    {
      keys: ["family", "spouse", "partner", "children", "dependent", "reunification"],
      html: `
        <p><strong>Family reunification</strong> is possible in most European countries, but the conditions depend on your permit, income, housing and the country.</p>
        <ul>
          <li>You usually need a valid residence permit, stable income, adequate housing and health insurance.</li>
          <li>Spouses may or may not get automatic work rights — check before assuming.</li>
          <li>Children generally get access to school, but enrolment timing matters.</li>
          <li>Some permits (for example certain Blue Cards) offer faster family reunification than others.</li>
        </ul>
        <p>Start the family application early: civil documents, apostilles and translations add weeks. The EU Immigration Portal has country-by-country summaries.</p>
        <p><a href="https://immigration-portal.ec.europa.eu/" target="_blank" rel="noopener noreferrer">EU Immigration Portal</a></p>`,
    },
    {
      keys: ["document", "documents", "apostille", "translation", "police", "certificate", "passport", "insurance"],
      html: `
        <p><strong>The document list is usually longer than the job offer.</strong> A typical file includes:</p>
        <ul>
          <li>Passport valid for at least six months, plus photos.</li>
          <li>Signed job offer or contract, with salary and role stated.</li>
          <li>Degree certificates, transcripts and professional registration.</li>
          <li>Sworn translations and, where required, apostille or legalisation.</li>
          <li>Health insurance, proof of accommodation, and sometimes a police clearance certificate.</li>
        </ul>
        <p>Keep high-quality scans in one folder and never send originals unless the authority explicitly asks. Requirements differ by country and permit type.</p>
        <p><a href="https://www.enic-naric.net/" target="_blank" rel="noopener noreferrer">ENIC-NARIC — qualification recognition</a></p>`,
    },
    {
      keys: ["how long", "timeline", "processing time", "weeks", "months", "wait", "start date"],
      html: `
        <p><strong>Plan for months, not days.</strong> A typical sequence runs: job offer → employer obtains or starts the work permit → you apply for an entry visa → you arrive → you register and collect the residence card.</p>
        <ul>
          <li>Two to six months is common; some countries and professions take longer.</li>
          <li>Appointment availability can be the slowest part — book as early as the system allows.</li>
          <li>Do not resign or book flights until the permit is confirmed in writing.</li>
          <li>Agree a realistic start date with the employer and keep them updated.</li>
        </ul>
        <p>Ask the employer whether they use a relocation provider and who pays the permit and visa fees. Get the answer in writing.</p>`,
    },
    {
      keys: ["housing", "rent", "apartment", "deposit", "anmeldung", "registration"],
      html: `
        <p><strong>Housing is often the hardest part of the move.</strong> Book a short-term place first, then search once you know the neighbourhoods and the commute.</p>
        <ul>
          <li>Expect a deposit of one to three months' rent and proof of income.</li>
          <li>Some countries require city registration within days of arrival (for example, Anmeldung in Germany).</li>
          <li>Never pay a deposit before viewing the property and seeing a written contract.</li>
          <li>Ask your employer about temporary housing or a relocation allowance.</li>
        </ul>
        <p>If an offer looks unusually cheap for the area, it probably is. Use official or well-known platforms and avoid WhatsApp-only landlords.</p>`,
    },
    {
      keys: ["scam", "fraud", "fake", "fee", "pay", "agency", "recruiter", "guarantee"],
      html: `
        <p><strong>No legitimate employer or public portal charges you for a job offer.</strong> Be cautious if anyone asks for money for a visa, a “guaranteed” contract, training, or a background check before an interview.</p>
        <ul>
          <li>Verify the company domain and the recruiter's email address.</li>
          <li>Cross-check the vacancy on the official national portal.</li>
          <li>Be wary of WhatsApp-only processes, crypto payments, gift cards and pressure to decide today.</li>
          <li>Read the contract: salary, role, location, hours, probation and who pays permit fees.</li>
        </ul>
        <p>If something feels wrong, stop and report it to the portal and local police. Keep copies of every message and payment request.</p>`,
    },
    {
      keys: ["recognition", "recognised", "regulated", "nurse", "doctor", "teacher", "electrician", "enic", "naric", "degree"],
      html: `
        <p><strong>Recognition is the gate for regulated professions.</strong> Nurses, doctors, teachers, electricians and many other roles need their qualification recognised by a national competent authority — not just a translated diploma.</p>
        <ul>
          <li>Start early: recognition can take weeks or months.</li>
          <li>ENIC-NARIC centres assess academic qualifications; regulated professions have their own authority.</li>
          <li>You may need syllabus details, proof of supervised practice, or a language certificate.</li>
          <li>Bridging courses or adaptation periods are sometimes required.</li>
        </ul>
        <p>Ask the employer which authority they accept before paying for translations or assessments.</p>
        <p><a href="https://www.enic-naric.net/" target="_blank" rel="noopener noreferrer">Find your ENIC-NARIC centre</a></p>`,
    },
    {
      keys: ["job seeker", "jobseeker", "look for work", "without a job", "opportunity card", "portugal job seeker"],
      html: `
        <p><strong>Some countries let you enter to look for work; most do not.</strong> Examples include Germany's Opportunity Card and Portugal's job-seeker visa. Austria has a job-seeker route for certain qualified people.</p>
        <ul>
          <li>You usually need proof of funds, health insurance, and a recognised qualification.</li>
          <li>A job-seeker visa does not guarantee a work permit — you still need to qualify once you have an offer.</li>
          <li>Check the maximum stay and whether it can be converted in-country.</li>
        </ul>
        <p>If your target country has no job-seeker route, apply from abroad for a role that sponsors the permit, or study/work in a country that offers a post-study stay.</p>
        <p><a href="https://www.make-it-in-germany.com/en/visa-residence/types/opportunity-card" target="_blank" rel="noopener noreferrer">Germany's Opportunity Card</a></p>`,
    },
    {
      keys: ["eu mobility", "another eu country", "move within europe", "schengen", "90/180", "switzerland", "uk", "brexit"],
      html: `
        <p><strong>“Europe” is not one immigration system.</strong> The EU sets a framework, but permits are issued nationally. Ireland is in the EU but not Schengen; Switzerland is in Schengen but not the EU; the UK is outside both.</p>
        <ul>
          <li>A Schengen visa is for visits, not work. The 90/180 rule does not grant work rights.</li>
          <li>Blue Card holders may have limited mobility to another EU country after a qualifying period, with conditions.</li>
          <li>Moving to a different country usually means a new permit application, even if you already live in the EU.</li>
        </ul>
        <p>Check both the country you are leaving and the country you are entering before you move.</p>`,
    },
  ];

  const log = $("#chat-log");

  function scrollChat() {
    log.scrollTop = log.scrollHeight;
  }

  function addMessage(html, who) {
    const node = document.createElement("div");
    node.className = `msg ${who}`;
    if (who === "user") {
      node.textContent = html;
    } else {
      node.innerHTML = html;
    }
    log.appendChild(node);
    scrollChat();
    return node;
  }

  function answerFor(question) {
    const text = question.toLowerCase();
    let best = null;
    let bestScore = 0;

    ADVISOR.forEach((entry) => {
      let score = 0;
      entry.keys.forEach((key) => {
        if (text.includes(key)) score += key.length;
      });
      if (score > bestScore) {
        best = entry;
        bestScore = score;
      }
    });

    if (best) return best.html;

    return `
      <p>I don't have a specific answer for that one yet, but I can help with the common threads:</p>
      <ul>
        <li><strong>Routes:</strong> EU Blue Card, national shortage permits, job-seeker visas.</li>
        <li><strong>Countries:</strong> Germany, Netherlands, Ireland, Austria, the Nordics and more.</li>
        <li><strong>Practicalities:</strong> documents, qualification recognition, salaries, family and timing.</li>
      </ul>
      <p>Try rephrasing with a country or a permit name — or browse the <a href="countries.html">country directory</a> for the official portal.</p>
      <p style="margin-top:8px;font-size:12px;color:var(--faint)">General guidance only. Confirm with the official authority.</p>`;
  }

  function sendMessage(text) {
    const message = String(text || "").trim();
    if (!message) return;

    addMessage(message, "user");
    $("#chat-input").value = "";

    const typing = document.createElement("div");
    typing.className = "msg bot typing";
    typing.innerHTML = "<i></i><i></i><i></i>";
    log.appendChild(typing);
    scrollChat();

    window.setTimeout(() => {
      typing.remove();
      addMessage(answerFor(message), "bot");
    }, 620);
  }

  $("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage($("#chat-input").value);
  });

  $$("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.getAttribute("data-prompt")));
  });

  /* ------------------------------------------------------------------ boot */

  fillForm(EJP.store.profile());
  updateProfilePreview();

  if (params.get("role") || params.get("company")) {
    activateTool("letter", { updateHash: false });
  } else {
    const hash = window.location.hash.replace("#", "");
    activateTool(validTools.includes(hash) ? hash : "cv", { updateHash: false });
  }
})();
