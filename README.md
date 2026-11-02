# EuroJobs Pro

EuroJobs Pro is a FastAPI job and volunteer board focused on listings with evidence of visa support. It includes separate search areas, Arabic/French/English UI, light/dark/system themes, user profiles, saved listings, CV and letter generation, and an optional Gemini assistant. It ships with an iOS application (Capacitor) that loads the hosted deployment and adds native Face ID lock, share, document export, offline handling and deep links.

## Run locally on Windows

Use Python 3.11 or newer. From this project folder, open PowerShell and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python manage.py init-db
python manage.py serve --reload
```

Open <http://127.0.0.1:8000>. The `--reload` option is for local development. Without it, use `python manage.py serve`.

### Run from VS Code

Open this folder in VS Code and install the **Python** extension. The included `.vscode/settings.json` points at `C:\Python315\python.exe` (change it if your Python lives elsewhere). Then either:

- Press **F5** and pick **EuroJobs Pro (uvicorn)** for a normal debug session, or **EuroJobs Pro (uvicorn --reload)** while editing templates and Python.
- Or open **Terminal > New Terminal** and run `python manage.py serve --reload`.

The debug configurations load `.env` automatically, enable Jinja template debugging, and serve the same site at <http://127.0.0.1:8000>. Stop any other server on port 8000 first. `Ctrl+C` in the terminal stops it.

The app starts without third-party keys. Search, pages, profiles, and saved data work locally; sources that need an API key are skipped until configured. With `ENABLE_SCHEDULER=true`, the app performs an initial listing ingestion and checks links in the background. It refreshes the official UK Home Office sponsor register on startup when the cached file is older than seven days, then checks weekly. You can refresh it manually with `python scripts/refresh_registers.py` or force a download with `python scripts/refresh_registers.py --force`.

## Configuration and API keys

If `.env` does not exist, copy `.env.example` to `.env`; keep an existing `.env` so its secrets are not overwritten. Never commit `.env` or paste secrets into chat.

- **Gemini (optional):** create a key in [Google AI Studio](https://aistudio.google.com/app/apikey), then set `GEMINI_API_KEY`. Model names and conservative request/day limits are configurable. Check current model availability and project quotas in [Gemini model docs](https://ai.google.dev/gemini-api/docs/models), [rate-limit docs](https://ai.google.dev/gemini-api/docs/rate-limits), and [AI Studio rate limits](https://aistudio.google.com/app/rate-limit). Gemini's free tier has its own data terms; review Google's current terms before sending personal information. The app is designed to omit profile contact details from model prompts.
- **Adzuna:** set both `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` from an Adzuna developer account.
- **Jooble:** set `JOOBLE_API_KEY` from Jooble's API programme.
- **Reed:** set `REED_API_KEY` if Reed API access is available to you.
- **ReliefWeb:** set `RELIEFWEB_APPNAME` for volunteer and humanitarian listings.
- **Alternative LLM providers:** `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are optional. `LLM_PROVIDER` selects the configured provider.
- **Logo service:** `LOGO_SERVICE_TOKEN` is optional; country flags and region icons are local fallbacks.

Arbeitnow, Remotive, RemoteOK, Jobicy, Himalayas, The Muse, and configured public employer ATS boards do not require these aggregator keys. Provider availability, rate limits, and their published data can change. `data/companies.yaml` currently contains 55 configured ATS boards; each is queried through its public endpoint, and a board failure does not stop other sources.

## Commands

```powershell
python manage.py init-db
python manage.py ingest
python manage.py ingest --source arbeitnow --pages 4
python manage.py check-links
python manage.py serve --host 127.0.0.1 --port 8000
python scripts/check_i18n.py
python -m pytest
```

The default database is `data/eurojobs.db` (SQLite). Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL for a PostgreSQL deployment. Back up the database and `static/logos/` if you need to preserve local data and cached logos.

## Deploy the web backend

The iPhone app loads the FastAPI deployment over HTTPS; Python cannot run on the phone. Deploy the backend first, then point the iOS shell at that origin.

### Docker

```powershell
docker build -t eurojobs-pro .
docker run -d --name eurojobs-pro -p 8000:8000 `
  -e SECRET_KEY="replace-with-a-long-random-string" `
  -e PUBLIC_BASE_URL="https://jobs.example.com" `
  -e SUPPORT_EMAIL="support@example.com" `
  -e APPLE_TEAM_ID="ABCDE12345" `
  -e DATABASE_URL="sqlite:////app/data/eurojobs.db" `
  -v eurojobs-data:/app/data `
  eurojobs-pro
```

Terminate TLS in front of the container (Caddy, nginx, Render, Fly.io or Cloud Run) and keep `/support` and `/legal` reachable without signing in. Set `PUBLIC_BASE_URL` to the final `https://` origin, because App Store links, notification payloads and the AASA file use it. Set `APPLE_TEAM_ID` (10-character Apple Developer Team ID) so `/.well-known/apple-app-site-association` is served for universal links. The container runs uvicorn with `--proxy-headers`, and session cookies switch to `Secure` when `X-Forwarded-Proto: https` is present.

### Render

`render.yaml` is a blueprint for a Docker web service with a persistent disk mounted at `/app/data`. Push the repository, choose **New > Blueprint** in Render, select the repository, then fill the `sync: false` values (`PUBLIC_BASE_URL`, `SUPPORT_EMAIL`, `APPLE_TEAM_ID`, `GEMINI_API_KEY`, `ADMIN_EMAILS`). After the first deploy, use the generated `https://*.onrender.com` hostname (or your custom domain) as `PUBLIC_BASE_URL` and as the iOS `EJP_APP_URL`.

## iPhone app (App Store)

`mobile/` contains the Capacitor 8 iOS project. It is not a second implementation: it hosts the same backend in a native shell and adds features the mobile website cannot provide:

- Face ID / Touch ID app lock for saved jobs and generated documents.
- Native share sheet for every listing.
- PDF and DOCX export through the Files/Share sheet.
- Offline screen with retry when the backend is unreachable.
- Native status bar, keyboard handling and safe-area insets.
- APNs registration hooks (the notification card stays hidden until server APNs settings exist).
- `eurojobspro://` deep links and universal links for jobs, volunteer placements and documents.

The shell contains no server secrets. AI and source keys stay in the backend environment.

### Prerequisites

- Node.js 22 or newer and npm.
- Apple Developer Program membership.
- A Mac with Xcode 16 or newer for local builds, or the GitHub Actions workflow below.
- A public HTTPS backend, as described in the previous section.

### Configure, sync and run

```powershell
cd mobile
npm ci
$env:EJP_APP_URL = "https://jobs.example.com"
npm run sync
npm run open:ios
```

On macOS use `export EJP_APP_URL=https://jobs.example.com` instead. `npm run sync` runs `scripts/prepare-web.mjs`, which writes `www/config.js` and rewrites `ios/App/App/App.entitlements` so the associated-domains host always matches `EJP_APP_URL`, then runs `cap sync ios`.

In Xcode select the **App** target, then:

1. **Signing & Capabilities**: choose your team, keep bundle identifier `com.eurojobspro.app` (or change it consistently here, in `capacitor.config.ts`, `render.yaml`, `IOS_BUNDLE_ID` and the workflow), and enable automatic signing.
2. Confirm **Associated Domains** contains the `applinks:` and `webcredentials:` entries for your host.
3. Set `MARKETING_VERSION` (for example `1.0.0`) and a unique `CURRENT_PROJECT_VERSION`.
4. Build on a device or simulator to verify Face ID, share, export and the offline screen.

The iPhone target is iPhone-only (`TARGETED_DEVICE_FAMILY = 1`), supports iOS 15+, declares `ITSAppUsesNonExemptEncryption = false`, ships `PrivacyInfo.xcprivacy`, and localises the bundle into English, French and Arabic.

### Build and upload with GitHub Actions

`.github/workflows/ios.yml` archives, exports an IPA and optionally uploads it to App Store Connect/TestFlight. It runs on `macos-15` via **Actions > iOS - build and upload to App Store Connect > Run workflow**, or when a tag such as `ios-v1.0.0` is pushed.

Repository **variables**:

| Name | Value |
| --- | --- |
| `EJP_APP_URL` | Public HTTPS backend origin, for example `https://jobs.example.com` |
| `IOS_BUNDLE_ID` | Optional, defaults to `com.eurojobspro.app` |

Repository **secrets**:

| Name | Value |
| --- | --- |
| `APPLE_TEAM_ID` | 10-character Apple Developer Team ID |
| `APP_STORE_CONNECT_KEY_ID` | App Store Connect API key ID |
| `APP_STORE_CONNECT_ISSUER_ID` | App Store Connect API issuer ID |
| `APP_STORE_CONNECT_PRIVATE_KEY` | Base64 of the `AuthKey_XXXXXXXXXX.p8` file |

Create the API key in **App Store Connect > Users and Access > Integrations > App Store Connect API** with an App Manager role. Encode it before saving the secret, for example `base64 -i AuthKey_XXXXXXXXXX.p8` on macOS or `[Convert]::ToBase64String([IO.File]::ReadAllBytes("AuthKey_XXXXXXXXXX.p8"))` in PowerShell. Never commit the `.p8` file.

The workflow always uploads the IPA as an artifact and uploads to TestFlight when `upload` is checked or the ref is an `ios-v*` tag. App Store signing needs the Apple team to own the bundle identifier and a distribution certificate/provisioning profile that Xcode can create automatically.

### App Store Connect checklist

1. **App record**: bundle ID `com.eurojobspro.app`, primary language English (U.S.), category Business, secondary category Productivity.
2. **Metadata**: paste the values from `mobile/appstore/metadata/en-US.json`, `fr-FR.json` and `ar-SA.json`. Field lengths are within Apple's limits.
3. **Screenshots**: `mobile/appstore/screenshots/iphone-6.9` are 1320x2868 and `iphone-6.5` are 1284x2778. Regenerate them against the production deployment:
   ```powershell
   cd mobile
   npx playwright install webkit
   $env:EJP_SCREENSHOT_URL = "https://jobs.example.com"
   npm run screenshots
   ```
   The board must contain real ingested listings before capturing; empty screenshots are not accepted as a useful app preview.
4. **App privacy**: answer the questionnaire with `mobile/appstore/privacy-answers.md`. It matches `ios/App/App/PrivacyInfo.xcprivacy`: no tracking, data linked to the user, used only for app functionality.
5. **Age rating**: 4+, no made-for-kids, no in-app purchases, no ads.
6. **Support and privacy URLs**: `https://<host>/support` and `https://<host>/legal` must open without signing in. The marketing URL is the site root.
7. **App Review Information**: use `mobile/appstore/review-notes.md`. Create a dedicated reviewer account with a filled profile and put its password only in App Store Connect.
8. **Guideline 4.2**: the review notes list the native features. Verify in the submitted build that Face ID lock, share, export and the offline screen work, so the app is not treated as a repackaged website.
9. **Placeholders**: replace `app.eurojobs.pro` with the real host everywhere (`EJP_APP_URL`, `PUBLIC_BASE_URL`, metadata URLs, entitlements). Re-run `npm run sync` after changing the host.

## How listing verification works

The board only displays active records with a sponsorship tier. Tier 1 means the employer matched an official register loaded from `data/registers/` for the listing's country; Tier 2 means the source gave an explicit visa-support flag or the posting contains a positive sponsorship phrase. Negative phrases override positive ones. A register listing shows that the employer has a licence; it does not prove that a specific vacancy qualifies. Always confirm support with the employer and relevant authority.

Volunteer listings use a separate search route, data details, fee filter, and visa-support classifier. Fee-charging programmes are hidden by default. Do not treat any opportunity as verified safe solely because it appears on this site.

The UK Home Office register is downloaded from its [official publication page](https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers) and cached locally. For other countries, add official CSV/JSON exports under `data/registers/` using the fields `company`, `country` (ISO 2-letter code), `route`, and `source`. Until a country register is available, listings there can still qualify at Tier 2 through explicit posting evidence.

## Privacy and important limits

- Listings come from third-party APIs and public employer ATS endpoints. Results depend on which sources are configured, reachable, and within their quotas; this project does not guarantee thousands of live listings.
- Listings, sponsorship phrases, employer-register matches, and volunteer details can be incomplete or stale. The badge is evidence-based, not a guarantee of a visa or job.
- Visa and immigration information is general and is not legal advice.
- CV and cover-letter generation requires an account/profile and an enabled AI provider. Review every generated document before use. Never enter passport, national ID, bank, or other sensitive data into AI features.
- English, French, and Arabic catalogs are present, with RTL layout for Arabic. Have native speakers review translations before public launch.
- For production, set a strong `SECRET_KEY`, configure HTTPS and a production ASGI server, review cookie/security settings and privacy obligations, and monitor provider attribution and limits. App Store reviewers expect the privacy policy and support page to stay online for as long as the app is available.

## Main folders

- `app/`: FastAPI routes, templates, data models, ingestion, search, visa classification, documents, and LLM integration.
- `app/sources/`: one adapter per public API or ATS provider.
- `data/i18n/`: English, French, and Arabic catalogs.
- `data/companies.yaml`: employer ATS boards.
- `data/registers/`: locally supplied sponsor-register files.
- `static/`: CSS, browser scripts, flags, region icons, and cached logos.
- `mobile/`: Capacitor iOS shell, native assets, App Store metadata, review notes, privacy answers and screenshot script.
- `mobile/ios/`: generated Xcode project (`App.xcodeproj`), `Info.plist`, `PrivacyInfo.xcprivacy` and `App.entitlements`.
- `mobile/appstore/`: listing metadata for en-US, fr-FR, ar-SA, plus App Store screenshots.
- `.github/workflows/ios.yml`: macOS build, IPA export and optional App Store Connect upload.
- `manage.py`: database, ingestion, link-check, and server commands.
- `tests/`: core regression tests.
