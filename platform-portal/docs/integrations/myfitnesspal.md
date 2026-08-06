# MyFitnessPal integration decision record

Research checked 6 August 2026. This is a product/engineering assessment, not legal advice.

## Decision

Build the user-uploaded Premium ZIP/CSV route now. Prepare an approved official API adapter, and offer printable-report/manual entry as fallbacks. Do not scrape public/shared diaries: the current Terms prohibit automated extraction and commercial use outside authorised commercial tools, irrespective of diary visibility.

## Official findings

- The [Developer Portal](https://www.myfitnesspal.com/apps/api/version) (accessed 6 August 2026) says the API is private, available only to approved developers, and directs applicants to `API@myfitnesspal.com` for the latest documentation and API Terms. Production credentials are not present here.
- The currently exposed developer material describes OAuth 2 authorization-code access with `client_id`, exact registered `redirect_uri`, scopes and `state`, and scopes named `diary`, `measurements`, `private-exercises`, and `subscriptions`. Because MyFitnessPal asks applicants to obtain the latest private documentation, PKCE support and current endpoint details are **unverified** and must not be assumed.
- [Data Export FAQs](https://support.myfitnesspal.com/hc/en-us/articles/360032273352-Data-Export-FAQs) (updated 9 January 2026; accessed 6 August 2026) says Premium users can export a chosen date range as a ZIP containing three CSVs: meal-level nutrition (macros, micronutrients, timestamps and food notes), progress/measurements, and exercise. The page does not mention Premium+ separately; Premium+ entitlement should be confirmed with MFP rather than inferred.
- [Free-version features](https://support.myfitnesspal.com/hc/en-us/articles/15457546881805-What-is-included-in-the-free-version) and [printable diary help](https://support.myfitnesspal.com/hc/en-us/articles/360032621691-Can-I-print-my-diary-from-the-app) (accessed 6 August 2026) document printable reports on the website and diary sharing for free users.
- [Diary visibility](https://support.myfitnesspal.com/hc/en-us/articles/360032273872-How-do-I-make-my-diary-visible-to-other-users) (updated 25 February 2026; accessed 6 August 2026) documents Public, Friends Only, and Locked-with-a-key settings. Viewing instructions involve MyFitnessPal UI/login; public visibility is not API permission.
- [Weight/diary privacy](https://support.myfitnesspal.com/hc/en-us/articles/360032274392-Can-other-members-see-my-weight-or-my-food-diary) (updated 25 February 2026; accessed 6 August 2026) says actual weight is always private and diaries are private by default.
- The [Terms of Service](https://www.myfitnesspal.com/terms-of-service) (effective 18 March 2025; accessed 6 August 2026) prohibit automated scraping/data extraction and commercial collection/use outside authorised commercial tools. This rules out a public-diary scraper for Traditional Strength without written permission.
- [Health Connect help](https://support.myfitnesspal.com/hc/en-us/articles/10553948248973-Health-Connect-FAQ-and-Troubleshooting) (updated 11 July 2025; accessed 6 August 2026) says logged calories are posted to Health Connect as meal summaries. It is a possible Android intermediary, not a complete cross-platform MFP export replacement.
- ICO guidance on [special-category rules](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-rules-on-special-category-data/) and [explicit consent](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-conditions-for-processing/) (accessed 6 August 2026) requires an Article 6 lawful basis plus an Article 9 condition. Explicit consent must be specific, affirmative, recorded, and withdrawable. Traditional Strength should document its Article 6 basis, retention schedule, processor contracts/transfers, data-subject rights and whether a DPIA is appropriate before beta.

## Public username test

No request was made for `geordiesteve547`. An automated request would itself be the prohibited automation the brief forbids. Therefore authentication-free accessibility, 2026 coverage, and structured-total consistency are **not established**. No personal data was downloaded or committed. Public/shared diary import is rejected unless MyFitnessPal supplies written commercial permission or approved API access.

## Recommendation matrix

| Path | Prototype | Production | Reliability | Athlete friction | Security/privacy | Maintenance | Status |
|---|---:|---:|---|---|---|---|---|
| Official API | blocked pending approval | 3–6 weeks after current docs/credentials | High if supported | Low | Medium; tokens/consent | Medium | Prepare |
| Premium ZIP/CSV | 1–3 days | 1–2 weeks | High for documented exports; fixture validation needed | Medium | Low–medium | Low | **Build now** |
| Uploaded printable PDF | 3–5 days | 2–4 weeks | Medium/low; layout and OCR variation | Medium | Medium | High | Defer |
| Public/shared diary | deceptively short | not viable | Low | Low | High | Very high | **Reject** |
| Apple Health / Health Connect | 1–2 weeks/platform | 4–8 weeks/platform | Medium; incomplete fields/directionality | Medium | Medium/high mobile permissions | Medium/high | Defer |
| Manual nutrition entry | already available | <1 week refinements | High technically, self-report dependent | High | Low | Low | Keep fallback |

## Implemented V1 contract

Accepted uploads are `.zip` or `.csv`, at most 10 MB. ZIPs permit at most ten members and 10 MB uncompressed; absolute/traversal paths are rejected. Files are parsed in memory and discarded immediately. Preview rows are stored temporarily in the database; committing or disconnecting clears them. Audit metadata (filename, SHA-256, status, timestamps, count, warnings/errors) remains until the athlete account-retention schedule deletes it; raw content does not.

Nutrition files require `Date` and at least one recognised nutrition total (`Calories`, `Protein (g)`, `Carbohydrates (g)`, `Fat (g)`; fibre optional). Meal rows are summed per day. Progress CSV weight is joined by date where present. Missing core macros are shown and the day marked partial; absent values are never inferred. The `(athlete, date, provider)` uniqueness rule makes re-imports updates, not duplicates, and import updates deliberately exclude notes.

Disconnect revokes the connection and deletes provider-derived daily records. Submitted weekly check-ins store snapshot averages and source/period metadata, so later imports cannot rewrite history. Coaches are authorised by the existing role middleware; athletes receive not-found responses for another athlete's URL. Existing global CSRF middleware protects all mutations.

Before production: move database/storage to encrypted infrastructure with private access; define backup erasure handling and a concrete audit retention period; add a DPIA/ROPA and privacy notice; validate columns against redacted genuine exports; consider malware scanning; and ensure operational logs never record bodies, parsed values, tokens or consent payloads.

CSV output is not part of V1. If added, prefix cells beginning `=`, `+`, `-`, `@`, tab or carriage return to prevent spreadsheet formula injection.

## Future official provider security design

Configuration names only: `MFP_API_ENABLED`, `MFP_CLIENT_ID`, `MFP_CLIENT_SECRET`, `MFP_REDIRECT_URI`, `MFP_AUTHORIZATION_URL`, `MFP_TOKEN_URL`, `MFP_API_BASE_URL`. Keep the stub disabled by default. After approval, use authorization code flow, exact HTTPS redirect URIs, cryptographically random single-use session-bound `state`, least-privilege read-only scopes, short-lived encrypted-at-rest tokens, refresh-token rotation/revocation, and no token logging. Use S256 PKCE **only if the current private documentation confirms support**; fail closed rather than silently omit a required control.

## Developer application email draft

Subject: MyFitnessPal API access request — Traditional Strength

Hello MyFitnessPal API team,

Traditional Strength is a UK strength-coaching platform helping coaches and adult athletes review training and voluntarily shared nutrition information. We plan an initial read-only beta with approximately 5–10 users, followed by a small controlled rollout.

We request current API documentation, API Terms, and approval for read-only diary/nutrition and measurement access (and subscription/entitlement metadata only if needed to explain feature availability). Each athlete would connect through MyFitnessPal authorization with explicit, granular consent. We will request only fields needed for daily/weekly coaching summaries and check-in pre-fill, will not request passwords, and will not make diagnoses or nutrition prescriptions.

Data will be isolated per athlete, visible only to that athlete and authorised coaches, encrypted in transit and at rest, and excluded from logs/public storage. Athletes can revoke access and request deletion; provider-derived data will be deleted on disconnect subject to a disclosed, minimal audit/backup retention policy. Submitted historical check-ins remain immutable snapshots and are clearly labelled by source.

Please advise on approval requirements, supported read-only scopes, OAuth/PKCE requirements, rate limits, webhook/sync options, data-retention obligations and branding/security review.

Kind regards,  
Traditional Strength
