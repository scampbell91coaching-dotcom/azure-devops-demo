# Traditional Strength platform accessibility audit

**Audit date:** 3 August 2026  
**Status:** documentation-only static review; not a compliance certification

## 1. Scope and standard used

This audit assesses the checked-in Traditional Strength public guides and coaching application, platform portal, coach workspace, athlete dashboard, weekly check-in, nutrition, programming, exercise library, navigation, forms, tables, controls, empty states, responsive CSS and relevant client-side behaviour.

The target is **WCAG 2.2 Level AA**, using the Web Content Accessibility Guidelines success criteria as the evaluation framework. Particular attention was given to 1.3.1 Info and Relationships, 1.4.3 Contrast (Minimum), 1.4.10 Reflow, 1.4.11 Non-text Contrast, 2.1.1 Keyboard, 2.4.1 Bypass Blocks, 2.4.3 Focus Order, 2.4.7 Focus Visible, 2.4.11 Focus Not Obscured (Minimum), 2.5.7 Dragging Movements, 2.5.8 Target Size (Minimum), 3.3.1 Error Identification, 3.3.2 Labels or Instructions, 3.3.3 Error Suggestion and 4.1.2 Name, Role, Value.

Review method: static inspection of HTML/Jinja, CSS and JavaScript. No production pages, authenticated real-data states, browser accessibility trees, keyboard sessions, zoom/reflow sessions, screen readers or automated accessibility scanners were run. Contrast ratios below are calculations from declared opaque foreground/background tokens; gradients, transparency, compositing, focus indicators and all rendered states still require browser measurement. Therefore this report does **not** claim automated or full WCAG compliance.

## 2. Existing strengths

- The public guide, coach and athlete base templates set `lang="en"`, unique page titles and responsive viewport metadata. The public, coach and athlete shells have main landmarks and visible-on-focus skip links ([public/base.html](../templates/public/base.html), [coach/base.html](../templates/coach/base.html), [athletes/base.html](../templates/athletes/base.html)).
- Public and coach navigation has an accessible name and exposes the current page with `aria-current="page"` ([public/base.html:36](../templates/public/base.html#L36), [coach/base.html:47](../templates/coach/base.html#L47)). The mobile coach menu is a native button with `aria-expanded` and `aria-controls`, updated by script ([coach/base.html:37](../templates/coach/base.html#L37), [coach_workspace.js:9](../static/js/coach_workspace.js#L9)).
- Most conventional forms use native labels, inputs, selects, textareas and buttons. The weekly check-in includes useful instructions, native ranges, input modes, persistent values and field-level error text ([checkins/form.html:2](../templates/checkins/form.html#L2)).
- The coaching application moves focus into each newly displayed step and focuses the first invalid field ([coaching_application.js:194](../static/js/coaching_application.js#L194), [coaching_application.js:217](../static/js/coaching_application.js#L217)). It also marks checked required fields with `aria-invalid`.
- Coach controls have a global `:focus-visible` rule, and the athlete/check-in shells provide explicit focus outlines ([coach_workspace.css:52](../static/css/coach_workspace.css#L52), [athlete_dashboard.css:1](../static/css/athlete_dashboard.css#L1), [checkins.css:13](../static/css/checkins.css#L13)).
- Dashboard and nutrition empty states generally use explicit, useful language rather than blanks, for example “No current programme”, “No check-ins yet” and “No nutrition data yet” ([athlete_dashboard.html:33](../templates/athletes/athlete_dashboard.html#L33), [nutrition/index.html:104](../templates/nutrition/index.html#L104)).
- Responsive breakpoints collapse most grids, and wide data regions generally use horizontal scrolling rather than clipping ([coach_workspace.css:586](../static/css/coach_workspace.css#L586), [programming.css:32](../static/css/programming.css#L32), [nutrition.css:21](../static/css/nutrition.css#L21)).

## 3. Critical blockers

These are release blockers for a broadly usable version 1, not a declaration that every occurrence is necessarily a legal conformance failure without rendered testing.

1. **Programming session fields have no programmatic names.** Column headings are visual `span` elements, while each existing row contains bare inputs/textarea; the new row relies on placeholders. Symbol-only drag, delete and add buttons are named “⋮⋮”, “×” and “+”, which do not communicate their action or row context reliably ([programming/session.html:65](../templates/programming/session.html#L65), [programming/session.html:81](../templates/programming/session.html#L81), [programming/session.html:113](../templates/programming/session.html#L113), and dynamically generated rows in [programming_pack2.js:150](../static/js/programming_pack2.js#L150)). This blocks 1.3.1, 3.3.2 and 4.1.2.
2. **Reordering is drag-only.** Rows are `draggable="true"`; the page advertises “Drag rows to reorder”, and no keyboard move-up/down control is present ([programming/session.html:56](../templates/programming/session.html#L56), [programming/session.html:81](../templates/programming/session.html#L81)). This blocks keyboard and non-drag operation under 2.1.1 and 2.5.7.
3. **The public coaching application suppresses the default outline and substitutes only a subtle border/background change.** The field rule declares `outline: none`; focus changes a 1px bottom border and 1% translucent background ([coaching_application.css:197](../static/css/coaching_application.css#L197), [coaching_application.css:225](../static/css/coaching_application.css#L225)). That is not a dependable visible focus indicator and is a 2.4.7/2.4.11 release risk across a primary public conversion flow.
4. **Form errors are not consistently associated or announced.** Coaching-application error nodes are not referenced with `aria-describedby`/`aria-errormessage` and are not live regions ([coaching_application.html:114](../templates/public/coaching_application.html#L114), [coaching_application.js:229](../static/js/coaching_application.js#L229)). The nutrition form's aggregate score error is plain text without `role="alert"`, focus management or a field association ([athletes/nutrition_checkin.html:33](../templates/athletes/nutrition_checkin.html#L33)). These failures can prevent assistive-technology users from discovering and correcting submission errors.

## 4. Keyboard-navigation findings

- **Pass by inspection:** primary links, form controls and menus use native interactive elements. Skip links exist in all newer user-facing shells. The wizard changes focus when steps change.
- **Blocker:** session row reordering has no keyboard alternative (see critical blocker 2).
- **High:** the programming spreadsheet has many anonymous controls, making tab navigation practically unusable even though controls are technically focusable. Add/delete controls also have small symbol-only targets; verify their rendered target is at least 24 by 24 CSS pixels (2.5.8).
- **High:** the coach mobile menu does not close with Escape, return focus to its trigger, or close after a menu choice; test whether an open sticky menu obscures focused content ([coach_workspace.js:1](../static/js/coach_workspace.js#L1), [coach_workspace.css:600](../static/css/coach_workspace.css#L600)).
- **Medium:** the external “Applications” link opens a new tab without warning in its accessible name or adjacent text ([coach/base.html:67](../templates/coach/base.html#L67)).
- **Medium:** legacy platform pages use a sidebar before the main region but provide no skip link, increasing repeated tab stops ([base.html:17](../templates/base.html#L17), [base.html:34](../templates/base.html#L34)).

## 5. Screen-reader findings

- Landmarks, page titles and top-level headings are generally sound in the public, coach and athlete shells. Decorative footer imagery correctly uses empty alternative text while the linked header logo has useful alt text ([public/base.html:29](../templates/public/base.html#L29), [public/base.html:63](../templates/public/base.html#L63)).
- **Critical:** programming spreadsheet inputs and icon controls lack names and row context (critical blocker 1).
- **High:** autosave state is a plain `span` without `role="status"` or `aria-live`, so asynchronous save/failure changes are unlikely to be announced ([programming/session.html:33](../templates/programming/session.html#L33)). Reorder/add/delete results also need concise live announcements.
- **High:** coaching application progress is visually encoded with classes but does not expose the current/completed step (`aria-current="step"` or equivalent). The bar has no progressbar semantics, value, minimum or maximum ([coaching_application.html:51](../templates/public/coaching_application.html#L51), [coaching_application.js:179](../static/js/coaching_application.js#L179)). The visible copy also says “Step 1 of 4” while the progress list contains five steps ([coaching_application.html:56](../templates/public/coaching_application.html#L56), [coaching_application.html:109](../templates/public/coaching_application.html#L109)).
- **High:** dynamically inserted field errors are neither live nor programmatically described by their fields. Moving focus helps, but the focused control will not necessarily announce the new reason for invalidity.
- **Medium:** coach metric collections are labelled visually but expressed as generic articles/divs. Consider lists or description lists where the label/value relation matters ([coach/dashboard.html:17](../templates/coach/dashboard.html#L17)).
- **Positive:** application completion and several platform loading states use `role="status"`/`aria-live="polite"` ([public/coaching_application.html:25](../templates/public/coaching_application.html#L25), [overview.html:23](../templates/overview.html#L23)).

## 6. Form-label and validation findings

- **Critical/high:** fix programming spreadsheet names and nutrition/application error associations described above.
- **High:** weekly check-in inputs always reference error IDs that are conditionally absent, producing broken ID references when there is no error (`training_adherence-error`, `week_ending-error`, etc.) ([checkins/form.html:5](../templates/checkins/form.html#L5), [checkins/form.html:13](../templates/checkins/form.html#L13), [checkins/form.html:33](../templates/checkins/form.html#L33)). Add the error ID only when rendered, or render a stable empty container. Add `aria-invalid="true"` only to invalid controls.
- **High:** the check-in error “summary” contains only a form-level string and no links to invalid fields ([checkins/form.html:28](../templates/checkins/form.html#L28)). On failed submission, focus a heading or summary, list every error, link each entry to its control, preserve values, and provide correction guidance.
- **High:** application validation checks only presence, not native validity such as malformed email or numeric range, because the form is `novalidate` and JavaScript uses `value.trim()` ([public/coaching_application.html:84](../templates/public/coaching_application.html#L84), [coaching_application.js:217](../static/js/coaching_application.js#L217)). Ensure client and server validation expose equivalent, specific errors.
- **Medium:** the exercise filter search and movement select have no labels; placeholder text is not a label ([exercises/index.html:125](../templates/exercises/index.html#L125)).
- **Medium:** many numeric forms state units but not valid ranges or scale meanings. Nutrition's 1–10 selects need instructions explaining endpoints; required status should be conveyed consistently ([athletes/nutrition_checkin.html:76](../templates/athletes/nutrition_checkin.html#L76)).
- **Positive:** the weekly check-in's score macro provides labels, scale help, limits and described errors; its checkbox wraps its complete visible label ([checkins/form.html:2](../templates/checkins/form.html#L2), [checkins/form.html:47](../templates/checkins/form.html#L47)).

## 7. Heading-structure findings

- Most primary pages have one clear `h1`, sections use `h2`, and nested content commonly uses `h3`. Coach and athlete dashboard empty states sit under their relevant section headings.
- **High:** the exercise-library results section begins with no heading; each result uses `h3` after the preceding “Add exercise” `h2`, creating an unclear outline and skipped contextual level ([exercises/index.html:125](../templates/exercises/index.html#L125), [exercises/index.html:157](../templates/exercises/index.html#L157)). Add a “Exercises” `h2` associated with the filter/results region.
- **Medium:** programming empty states are bare paragraphs (“No blocks yet”, “No weeks yet”), while comparable dashboard states use headings. Give each results region a stable heading and announce state changes when filtering ([programming/index.html:17](../templates/programming/index.html#L17), [programming/block.html:5](../templates/programming/block.html#L5)).
- Do not use `.eyebrow` spans/paragraphs as substitutes for structural headings. Retain the generally correct page `h1` → section `h2` → item `h3` hierarchy when remediating.

## 8. Colour and contrast findings

Static token calculations show strong text contrast for major opaque pairs: coach muted `#aaa99e` on coach background `#0b0d0c` is approximately **8.24:1** (and 7.65:1 on panel `#131715`); athlete muted `#9aa7b8` on `#08111f` is **7.74:1**; public-guide muted `#aaa398` on `#070707` is **8.06:1**; legacy muted `#9cb0ca` on `#07111f` is **8.55:1**. Token sources: [coach_workspace.css:3](../static/css/coach_workspace.css#L3), [athlete_dashboard.css:1](../static/css/athlete_dashboard.css#L1), [public_guides.css:3](../static/css/public_guides.css#L3), [styles.css:2](../static/styles.css#L2).

Risks requiring rendered verification:

- White text `#fff` on the fallback blue `#4f8cff` is approximately **3.22:1**, below 4.5:1 for normal text. It appears in recommendation and lead-magnet primary controls ([recommendations.css:93](../static/css/recommendations.css#L93), [lead_magnet.css:81](../static/css/lead_magnet.css#L81)). The active runtime accent may differ; test the computed colour.
- Application optional-label text `#767168`, placeholder `#5f5b54`, error colours, translucent borders and the 1% focus background need computed-style contrast tests against their actual backgrounds ([coaching_application.css:192](../static/css/coaching_application.css#L192), [coaching_application.css:214](../static/css/coaching_application.css#L214)). Placeholder contrast is still subject to 1.4.3 when it conveys information.
- Status colours are accompanied by text in reviewed templates, which avoids colour-only meaning. Still measure border/focus/control boundaries against adjacent colours for 1.4.11, including disabled navigation and form borders.
- Test forced-colours/high-contrast mode and do not rely on `color-mix()` alone for athlete status boundaries ([athlete_dashboard.css:1](../static/css/athlete_dashboard.css#L1)).

## 9. Focus-state findings

- Coach, athlete and check-in surfaces define visible focus. The coach focus token (`#e2bd7f`) is visually distinct and the skip links become visible on focus.
- **Blocker:** application form focus is insufficiently explicit because the default outline is removed (critical blocker 3). Use a consistent 2px-or-stronger outline with adequate 3:1 adjacent contrast and preserve it in forced-colours mode.
- **High:** legacy portal CSS defines hover/active navigation styling but no focus-visible rule ([styles.css:13](../static/styles.css#L13)). Add a shared keyboard focus treatment for all links, buttons and controls.
- **Medium:** programming spreadsheet overrides field focus with an inset (`outline-offset: -2px`) accent outline; test clipping and 3:1 contrast, particularly inside horizontally scrolled cells ([programming_pack2.css:101](../static/css/programming_pack2.css#L101)).
- Test sticky header overlap and ensure focused targets are not fully obscured at desktop and mobile widths (2.4.11).

## 10. Table and data-display findings

- Native tables and `thead` are used for coach, nutrition and platform datasets, and wrappers allow horizontal scrolling.
- **High:** reviewed tables do not declare `scope="col"` on column headers or provide captions/accessible names ([coach/dashboard.html:118](../templates/coach/dashboard.html#L118), [nutrition/index.html:68](../templates/nutrition/index.html#L68), [athletes/list.html:90](../templates/athletes/list.html#L90), [history.html:78](../templates/history.html#L78)). Add a descriptive `caption` (visually hidden if appropriate) and explicit scopes; add row headers where athlete/date identifies the row.
- The programming “sheet” is a CSS grid of generic divs rather than a semantic table, and its visual headers are not associated with fields ([programming/session.html:65](../templates/programming/session.html#L65)). Prefer a real table when the data model is tabular, or give every input an explicit per-row label and programmatic relationship.
- Do not solve mobile tables by hiding columns that contain essential information. Preserve reading order, make the scroll region keyboard-focusable only when needed, label it, and provide an instruction that more columns are available horizontally.

## 11. Mobile accessibility

- Responsive grid collapse is broadly thoughtful across coach, exercise, programming, nutrition and athlete pages. The athlete section links intentionally scroll horizontally rather than wrap or clip.
- **High:** the programming sheet has a fixed `min-width: 1180px` ([programming_pack2.css:52](../static/css/programming_pack2.css#L52)). Although its container scrolls, completing a nine-column form at 320 CSS pixels or 400% zoom is burdensome and may fail meaningful reflow. Provide a stacked/card editor or focused single-row editing mode at narrow widths.
- **High:** the public guide navigation is hidden below 700px ([public_guides.css:439](../static/css/public_guides.css#L439)). Verify that every hidden destination remains available through an equivalent visible mobile control; footer links occurring after the entire page are not an equivalent primary navigation experience.
- **Medium:** coach mobile navigation requires JavaScript and lacks Escape/focus-return behavior. Verify it at 320 CSS pixels, 200% and 400% zoom in portrait/landscape.
- Verify touch targets (minimum 24 by 24 CSS pixels, with spacing exception as applicable), on-screen keyboard behavior, zoom without loss, horizontal scrolling limited to genuine data tables, and that sticky headers do not cover focused controls or errors.

## 12. Exact file-reference index

| Surface | Primary evidence files |
|---|---|
| Public guides/application | [public/base.html](../templates/public/base.html), [public/coaching_application.html](../templates/public/coaching_application.html), [public_guides.css](../static/css/public_guides.css), [coaching_application.css](../static/css/coaching_application.css), [coaching_application.js](../static/js/coaching_application.js) |
| Legacy platform portal | [base.html](../templates/base.html), [styles.css](../static/styles.css), [overview.html](../templates/overview.html), [history.html](../templates/history.html) |
| Coach/dashboard/navigation | [coach/base.html](../templates/coach/base.html), [coach/dashboard.html](../templates/coach/dashboard.html), [coach_workspace.css](../static/css/coach_workspace.css), [coach_workspace.js](../static/js/coach_workspace.js) |
| Athlete/check-in/nutrition | [athletes/base.html](../templates/athletes/base.html), [athletes/athlete_dashboard.html](../templates/athletes/athlete_dashboard.html), [checkins/form.html](../templates/checkins/form.html), [athletes/nutrition_checkin.html](../templates/athletes/nutrition_checkin.html), [nutrition/index.html](../templates/nutrition/index.html) |
| Programming/exercises | [programming/session.html](../templates/programming/session.html), [programming/week.html](../templates/programming/week.html), [programming_pack2.js](../static/js/programming_pack2.js), [programming_pack2.css](../static/css/programming_pack2.css), [exercises/index.html](../templates/exercises/index.html) |

## 13. Prioritised remediation plan

### P0 — before version 1

1. Give every programming-sheet input and button a unique accessible name including row/exercise context; connect column meaning semantically.
2. Add keyboard and single-pointer alternatives to drag reordering (Move up/Move down), maintain focus after actions, and announce reordered/added/deleted/saved states.
3. Restore a robust application focus-visible indicator and verify it in normal and forced-colours modes.
4. Standardise error handling: summary with linked errors, field `aria-invalid`, stable `aria-describedby` or `aria-errormessage`, actionable copy, preserved values and focus to the summary/first error.
5. Make the session editor workable at 320 CSS pixels/400% zoom without two-dimensional form scrolling.

### P1 — immediately after blockers

1. Add table captions, column scopes and row headers.
2. Label exercise filters and explain numeric scales/ranges.
3. Expose wizard step state and consistent “of 5” copy; announce dynamic state changes.
4. Add legacy portal skip/focus treatments and complete mobile-menu keyboard behavior.
5. Measure all computed colour pairs, component boundaries and focus indicators; correct any failures and document approved tokens.

### P2 — later improvement

1. Improve semantic grouping of metric cards and empty/result regions.
2. Warn about links that open new windows and refine mobile navigation equivalence.
3. Add reduced-motion, forced-colours, speech-input and cognitive-usability checks; simplify dense programming terminology and provide help where users need it.

## 14. Playwright accessibility-test plan

Playwright should provide repeatable evidence, not a compliance claim. Add `@axe-core/playwright` scans to representative seeded states and supplement them with semantic and interaction assertions.

Test matrix:

- Public hip/shoulder guides, application steps 1–5, invalid application, submitted application.
- Coach dashboard with populated and empty queues; athletes list; nutrition populated/empty.
- Athlete dashboard with/without programme/check-ins/nutrition; valid and invalid weekly/nutrition forms.
- Exercise library populated/no results/edit; programming block/week/session populated and empty.
- Legacy overview/history and each controls table.
- Chromium, Firefox and WebKit; desktop 1280×800 and mobile 320×568/390×844; repeat key pages with forced colours where supported.

Automated assertions:

1. Run axe after initial render and after every wizard/menu/error/empty-state transition; fail on serious/critical violations and maintain reviewed exceptions with owner and expiry.
2. Assert one main landmark, one page `h1`, non-empty unique title, valid heading sequence, labelled navs/forms/tables, no duplicate IDs and no unresolved IDREFs (`aria-describedby`, `aria-controls`, etc.).
3. Tab from the document start: skip link becomes visible and moves focus to main; every actionable control receives visible focus; focus order follows visual/task order; no focus is obscured.
4. Operate mobile menu, wizard, check-in submission and complete programming add/edit/delete/reorder using keyboard only. Assert Escape/return-focus behavior and stable focus after DOM updates.
5. Capture accessible names/roles for every programming row control; assert names include field and row/exercise. Assert `aria-expanded`, `aria-current`, `aria-invalid` and live-region updates.
6. Submit each form empty and with malformed/out-of-range values; assert summary focus, links to fields, announced specific errors, preserved valid data and successful resubmission.
7. At 320 CSS pixels and emulated 400% zoom, assert no document-level horizontal overflow and no clipped control/error; permit labelled table-region scrolling. Take screenshots for human review.
8. Use browser-evaluated computed colours plus a contrast helper for known opaque text/background and focus/boundary pairs. Keep manual checks for gradients/transparency/imagery.

Manual evidence still required: NVDA + Firefox and JAWS + Chrome on Windows; VoiceOver + Safari on macOS and iOS; TalkBack + Chrome on Android; keyboard-only and switch-equivalent navigation; 200%/400% zoom; reflow; forced colours; speech control; target size; reading and error comprehension. Record browser, assistive technology version, viewport, dataset, steps, expected/actual result, screenshot/video and issue link.

## 15. Acceptance criteria

Version 1 is acceptable for release only when:

- All P0 findings are fixed and retested; no known WCAG 2.2 A/AA blocker prevents completion of a core public, coach or athlete task.
- Every interactive control has a meaningful name, role and state; programming controls include row context.
- Every core workflow is completable keyboard-only without dragging, with logical order, persistent visible focus and no focus trap/obscuring.
- Invalid submissions produce a focused/announced summary, linked field errors, `aria-invalid`, specific correction guidance and preserved valid input.
- Page landmarks, titles, one `h1`, section hierarchy, labels, table captions/scopes and ID references pass automated assertions and manual accessibility-tree review.
- Normal text is at least 4.5:1 (3:1 for qualifying large text); UI boundaries and focus indicators are at least 3:1 where WCAG requires; information is not colour-only.
- Core pages work at 320 CSS pixels and 400% zoom without loss of content/function or page-level two-dimensional scrolling, except accessible data-table regions.
- Axe finds no unreviewed serious/critical issues on the defined matrix. This is a quality gate only, not proof of WCAG conformance.
- The screen-reader/manual matrix has evidence for all critical journeys and no unresolved severity-1/2 defect.

## 16. Version 1 blockers versus later improvements

| Version 1 blockers | Later improvements |
|---|---|
| Programming-sheet names/relationships and understandable add/delete controls | Richer metric/list semantics and more descriptive empty-state structure |
| Keyboard/non-drag row reordering with focus preservation and announcements | New-window link warnings and refined mobile navigation ergonomics |
| Robust coaching-application focus indicator | Expanded reduced-motion, speech-input and cognitive walkthroughs |
| Consistent, associated and announced errors in application, weekly check-in and nutrition forms | Broader browser/assistive-technology regression coverage beyond the core matrix |
| Narrow-screen/400%-zoom programming workflow | Progressive enhancement of dense programming help and terminology |
| Verified accessible names, contrast and keyboard completion on every core journey | P2 polish that does not block task completion or understanding |

Any unresolved A/AA failure discovered by the planned rendered or assistive-technology testing becomes a version 1 blocker when it prevents or materially impairs a core task, regardless of whether it appears in the static-review list above.
