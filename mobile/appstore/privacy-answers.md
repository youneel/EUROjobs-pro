# App Store Connect — App Privacy answers

Use these answers in **App Store Connect → App Privacy**. They match
`ios/App/App/PrivacyInfo.xcprivacy`.

## Tracking

- **Does the app track users?** No.
- **Tracking domains:** none.

## Data collected

All items are **linked to the user's identity**, used only for **App Functionality**, and
are **not used for tracking**.

| App Store Connect data type | Collected | Notes |
| --- | --- | --- |
| Name | Yes | Profile full name, used in generated documents |
| Email Address | Yes | Account sign-in and support |
| Phone Number | Yes | Optional profile field; never sent to the AI model |
| Physical Address | Yes | Optional profile address; never sent to the AI model |
| User ID | Yes | Account identifier and session |
| Other User Content | Yes | CV/letter content, saved listings, chat messages |
| Product Interaction | Yes | Saved listings and document history |
| Other Data Types | Yes | Date of birth, nationality, ID number, target countries, visa preferences |

Not collected: health, fitness, payment, credit, precise or coarse location, contacts,
photos, audio, advertising data, crash data, performance data, search history,
browsing history, gameplay content.

## Purposes

- App Functionality — all of the above.
- Analytics — none.
- Advertising — none.
- Personalisation — none beyond applying the user's own search filters.

## Third parties

- **Google Gemini** processes only the profile fields needed to draft a requested
  document or answer an assistant message. Contact details, ID numbers and exact date of
  birth are stripped before the request. When `GEMINI_FREE_TIER` is true, Google's free
  tier terms apply; this is disclosed in the app and privacy policy.
- **Hosting provider** stores the database and serves the site over HTTPS.
- No advertising, analytics or attribution SDKs are included.

## Data retention and deletion

- Users can delete their account and all linked content in **Profile → Delete my data**.
- Deletion removes the profile, documents, saved listings, chat sessions, AI cache rows
  and push tokens.
- Users can also request deletion by email from the Support page.
- Server logs are rotated and used only for security and reliability.

## Encryption

- The app sets `ITSAppUsesNonExemptEncryption = false`.
- All network traffic uses HTTPS/TLS provided by the operating system and the hosting
  provider. No custom or proprietary encryption is implemented.
- Face ID / Touch ID results are handled by iOS; the app stores only an on/off flag.

## Account deletion

- In-app path: **Profile → Delete my data** (available without contacting support).
- Public explanation: https://app.workatlas.pro/support

## Age rating

- **4+**. No violence, gambling, contests, user-generated public content, or unrestricted
  web access. External employer links open in the system browser.
