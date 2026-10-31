# EuroJobs Pro

An Apple-inspired, dependency-free take on a European jobs and visa-mobility platform. The site pairs a curated job board and official-portal directory with a local CV studio, cover-letter generator and plain-language visa advisor.

Everything runs in the browser. There is no build step, account system, database or remote AI service.

## Run it locally

From this folder, start any static file server. For example:

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173>.

If Python is available on your PATH, `npm start` runs the same command.

Opening `index.html` directly also works, but a local server gives the most predictable behaviour for URL state, downloads and clipboard access.

## Pages

| File | Purpose |
| --- | --- |
| `index.html` | Landing page: hero, promo tiles, journey, country carousel and manifesto. |
| `jobs.html` | Searchable job board with country, profession, visa and saved filters, sorting, URL state and a detail drawer. |
| `countries.html` | Directory of 31 public employment portals with live search and region filters. |
| `tools.html` | CV Studio, cover-letter generator and local visa advisor. |
| `legal.html` | Privacy, terms, storage and accessibility notes. |

## What is local

- `ejp_saved_v1` stores saved roles.
- `ejp_profile_v1` stores the CV profile.
- Cover letters are generated on the device and are not persisted; copy or download them if you want to keep them.
- The advisor uses a built-in knowledge base, not a model or API.
- PDF CVs are read in the browser with pdf.js loaded on demand from cdnjs. TXT and Markdown work without that request.
- Google Fonts is optional; the design falls back to system fonts if the request is blocked.

## Data and disclaimers

All listings, companies, salaries, profiles and stories are illustrative. Visa routes and advisor answers are general information, not legal or immigration advice. Every role links to a real public employment portal, where the vacancy and current requirements should be verified.

## Structure

```text
.
├── index.html
├── jobs.html
├── countries.html
├── tools.html
├── legal.html
├── assets/
│   ├── data.js       # country, portal, job and role data
│   ├── styles.css    # design system, responsive and print styles
│   ├── site.js       # shared storage, navigation and UI helpers
│   ├── jobs.js       # job filtering, cards and detail drawer
│   ├── countries.js  # portal search and region filtering
│   └── tools.js      # CV parsing, letters and advisor
└── package.json      # optional `npm start` shortcut
```

## Before publishing

- Replace illustrative listings and statistics with verified data.
- Add a monitored contact and data-controller identity to `legal.html`.
- Self-host fonts and pdf.js if third-party requests are not acceptable.
- Re-test forms, print output, deep links and the official portal URLs.
"# EUROjobs-pro" 
