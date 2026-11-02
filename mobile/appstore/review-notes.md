# App Review notes — WorkAtlas 1.0

Paste the relevant parts into **App Store Connect → App Review Information → Notes**.
Do not commit a real password to this repository.

## What the app is

WorkAtlas is a job board for roles and volunteer placements that show evidence of
visa sponsorship. Listings are ingested from official job APIs and public employer
career pages; the app never scrapes LinkedIn, Indeed or Glassdoor. Each listing is
classified into Tier 1 (employer matched an official government sponsor register) or
Tier 2 (the posting explicitly mentions sponsorship). Unsupported listings are hidden.

## Why this is not a repackaged website (Guideline 4.2)

The iOS app is a native Capacitor shell around the same account and listing backend.
It adds functionality that the mobile website cannot provide:

1. **Face ID / Touch ID app lock.** A per-device switch in Profile protects saved jobs
   and generated CVs on a shared phone. The biometric prompt is handled entirely by
   iOS; the app only stores a boolean preference in `UserDefaults`.
2. **Native share sheet.** Every listing has a Share button that opens
   `UIActivityViewController` with the role, company and URL.
3. **Native document export.** CVs and cover letters are downloaded inside the app and
   handed to the Files/Share sheet via the Filesystem and Share plugins, so users can
   save them to iCloud Drive or email them.
4. **Push notifications.** Job alerts are registered through APNs when the deployment
   has APNs configured (the card is hidden otherwise).
5. **Native lifecycle.** Status bar and keyboard are managed by the shell, safe-area
   insets are respected, and an offline screen with a retry action is shown when the
   backend cannot be reached.
6. **Deep links.** `workatlas://` and universal links open the matching job,
   volunteer or document page inside the app.

The shell points at a hosted HTTPS deployment because the Python/FastAPI backend cannot
run on the device. The offline screen, native lock, share, export and push features are
implemented in the iOS target, not in the website.

## Review steps

1. Launch the app. The home page loads over HTTPS.
2. Browse **Jobs** and **Volunteer** without signing in.
3. Open any listing → **Share** → the iOS share sheet appears.
4. Sign in with the review account below.
5. Open **Profile** → enable **Unlock with Face ID or Touch ID** → background the app for
   more than one minute → return and unlock.
6. Open **Documents** → create a CV or cover letter → **Export PDF** → the file is handed
   to the share/save sheet.
7. Delete the account with **Profile → Delete my data**. This removes the profile,
   documents, saved jobs, chat history and push token.

## Demo account

Create a dedicated account before submitting and enter it only in App Store Connect:

- Email: *(set in App Store Connect)*
- Password: *(set in App Store Connect)*

The account must have a filled profile with at least one experience entry so the
document generator has verifiable content. AI features require `GEMINI_API_KEY` on the
server; if AI is disabled the rest of the app still works, but review the listing text
before submitting.

## Content and safety

- No user-generated public content, no comments, no messaging between users, no ads.
- No in-app purchases and no subscriptions.
- No tracking SDKs. The privacy manifest declares no tracking and no tracking domains.
- Visa badges are evidence-based, not legal advice, and the UI repeats that disclaimer.
- AI drafting only uses profile fields the user enters; contact details, ID numbers and
  exact date of birth are excluded from prompts. Each draft is verified against the
  profile and regenerated once if unsupported content is detected.
- Account deletion is available in-app and also by email from the Support page.

## Contact

Support: support@workatlas.pro
Privacy: https://app.workatlas.pro/legal
Support page: https://app.workatlas.pro/support

## Before you submit

- Replace `app.workatlas.pro` with the real deployment hostname everywhere
  (`EJP_APP_URL`, `PUBLIC_BASE_URL`, entitlements, metadata URLs).
- Configure at least one listing source and run ingestion so the board is not empty.
- Configure `GEMINI_API_KEY` if the listing mentions AI features.
- Capture screenshots from the production build (see `screenshots/README.md`).
- Confirm the privacy policy and support page are reachable without signing in.
