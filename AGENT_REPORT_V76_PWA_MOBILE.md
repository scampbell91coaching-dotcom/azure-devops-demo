# Agent C report — V7.6 PWA and mobile readiness

## Outcome

Completed a design-only repository audit and produced the detailed readiness plan in `docs/v7.6-pwa-mobile-readiness.md`.

The current athlete portal is a solid responsive Flask/Jinja experience, but it is not an installable PWA. The recommended boundary is a staged responsive-web → installable-PWA → Capacitor-shell → closed app-store-beta path, with private athlete data remaining network-only and `no-store` through the initial PWA release.

## Key findings

- Mobile athlete surfaces have a purpose-built bottom navigation, sticky session actions, appropriate input modes, narrow-screen breakpoints, and Playwright coverage at 320, 390, and 430 px.
- Real-device gaps remain: safe-area insets, virtual keyboards, standalone display, dynamic text, orientation, connectivity, and observed in-session usability.
- Authentication uses Flask's signed client-side cookie with `Secure`, `HttpOnly`, `SameSite=Lax`, CSRF enforcement, and an eight-hour absolute age check. Login clears prior session state; logout is POST/CSRF protected.
- Same-origin protected deep links already survive login using a validated `next` path, including current-session routes.
- Every private-app response currently receives `Cache-Control: no-store`, including static assets. This is safe for data but prevents efficient immutable asset caching.
- There is no manifest, service worker, install/update UX, offline page, build-version browser contract, or PWA icon family.
- The only current image is a roughly 651 KB 1170×1675 RGB portrait logo, unsuitable by itself as square/maskable/touch artwork.
- CSP is strong and compatible with same-origin PWA components. It should add explicit `manifest-src`/`worker-src`, retain external scripts, and must not gain `unsafe-inline`/`unsafe-eval`.
- Existing JSON routes are mainly coach/platform operations, not a supported athlete mobile contract.

## Safety decisions

Never cache authenticated HTML/JSON, auth/account-token responses, programme/prescription/session data, training logs, check-ins, nutrition/bodyweight/imports, coach feedback, profile data, coach/operations pages, video metadata/URLs, errors, redirects, or mutations. Only build-versioned generic CSS, JavaScript, icons, fonts, branding, and a generic offline page are safe initial worker-cache candidates.

The initial offline experience should be a generic connectivity shell. Optional offline current-session drafts require a separate threat model, minimal versioned IndexedDB storage, explicit device disclosure/removal, short TTL, clearing on logout/account switch/expiry/completion, server revisions, idempotency keys, conflict handling, and explicit online completion. No automatic mutation replay is recommended.

For future video, the backend may authorize a short-lived, one-object upload grant and record metadata. The browser/native client must upload directly to private object storage. Flask/Gunicorn must never proxy video bytes, and AKS/app filesystems or pod volumes must never store them. No video or Azure resources were implemented.

## Proposed API boundary

Keep SSR for login/recovery, dashboard/programme, check-ins, nutrition, imports, and coach workflows during PWA delivery. Add only demonstrated athlete seams, deriving athlete identity from the authenticated principal:

- `GET /api/v1/athlete/me`
- `GET /api/v1/athlete/today`
- `GET /api/v1/athlete/programme`
- `GET /api/v1/athlete/sessions/<id>`
- later, revision-aware/idempotent draft save and explicit session completion

Cookie + CSRF remains the recommended first Capacitor authentication model, subject to iOS/Android persistence and logout testing. Native token authentication would be a separate identity project.

## Recommended first backlog slice

1. Split cache policy by sensitivity and add negative cache tests.
2. Introduce revisioned static URLs.
3. Fix safe-area/keyboard behavior and broaden mobile E2E coverage.
4. Create proper square, maskable, and Apple touch artwork.
5. Add a validated manifest.
6. Add an allowlisted minimal service worker and generic offline page.
7. Add deterministic update/version handling and Cache Storage assertions.
8. Run a real-device install/standalone matrix before considering Capacitor.

## Restrictions observed

No application implementation, app-store submission, video implementation, Azure storage creation, production manifest/GitOps change, merge, or deployment was performed.
