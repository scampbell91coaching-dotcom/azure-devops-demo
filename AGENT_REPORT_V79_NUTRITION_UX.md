# V7.9 Nutrition UX agent report

## Delivered

- Audited the live coach nutrition overview, coach athlete record/review flow, athlete dashboard, dedicated and weekly check-ins, MyFitnessPal import, bodyweight projections, entitlement gating, and responsive nutrition styles.
- Audited the schema-independent macro-prescription and meal-plan foundations.
- Added `docs/v7.9-nutrition-ux.md` with the canonical information architecture, language, workflows, state model, comparison rules, disabled-entitlement historical-read behavior, and implementation sequence.
- Defined explicit desktop and 430/390/320 px acceptance criteria, including accessibility, source/coverage, conflict, partial-data, and history-only states.

## Principal decisions

- **Targets**, **Meal plan**, **Actual intake**, and **Nutrition check-in** are separate records and visible nouns. Bodyweight is a dated outcome signal; adherence/review is retrospective evidence.
- Training/rest targets resolve for a known day type; an unknown day type uses the explicit daily fallback and is never inferred from nearby training.
- A meal plan is optional and subordinate to an immutable target snapshot. Imported daily totals can corroborate macro intake but cannot prove meal-plan completion.
- Current comparisons require an applicable dated target, actual data, visible source, and stated coverage. Missing values never become zero, and no adherence percentage is shown before a coverage policy is agreed.
- Historical check-in target columns are labelled **Reported target (legacy snapshot)** rather than presented as the prescription source of truth.
- Disabled nutrition coaching retains coach-readable history behind a persistent **Nutrition coaching ended · History only** state. All mutations and active review tasks are removed; re-enablement does not silently reactivate an ended prescription or assignment.

## Scope and prototype decision

No persistence, migration, route, service, or production change was made. No template prototype was added: prescriptions and meal-plan assignments currently have no live view model or route, so invented template data would imply capabilities and state that do not exist. The documentation is the isolated, low-conflict handoff for the persistence/UI slices.

## Verification

- Reviewed the rendered-template inputs and responsive CSS contracts in the repository.
- Checked document links/paths and whitespace with Git.
- No runtime test was required because the change is documentation-only.

## Recommended next slice

Agree the immutable prescription/assignment persistence and authorization contract, then implement coach target revisions and an athlete read-only current-target panel. Keep legacy check-in target entry until that source of truth is live and a separately reviewed deprecation plan exists.
