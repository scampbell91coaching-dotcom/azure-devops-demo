# Agent B report: Nutrition / Macro Prescription foundation

## Completed

- Inspected existing nutrition check-in, weekly check-in, nutrition import,
  dashboard service, athlete routes, templates, migrations, and related tests.
- Added the schema-independent domain and service in
  `platform-portal/portal/services/nutrition_prescriptions.py`.
- Added daily targets, optional training/rest variants, inclusive effective
  dates, optional fibre/meal count/notes, validation, and auditable provenance.
- Added a repository protocol and in-memory adapter as persistence seams.
- Kept prescriptions structurally separate from actual intake and adherence.
- Added focused unit tests in
  `platform-portal/tests/test_nutrition_prescriptions.py`.
- Documented future persistence and coach/athlete UX integration seams in
  `platform-portal/docs/v7.3-nutrition-macro-domain.md`.

## Key decisions

- Default daily targets are mandatory; training and rest values are optional
  overrides and fall back to daily targets.
- Effective date bounds are inclusive. Overlap for one athlete is rejected so
  target resolution cannot silently pick between competing sources of truth.
- Prescriptions contain no actual intake, bodyweight, wellbeing, or adherence.
- Calorie-to-macro arithmetic is not enforced because it is not a reliable data
  integrity invariant.
- Existing check-in target columns remain untouched for compatibility. A future
  migration should stop collecting copied targets and resolve them by date.

## Verification

Focused test command:

```text
cd platform-portal
pytest -q tests/test_nutrition_prescriptions.py
```

Focused result: `13 passed`.

Full portal regression command:

```text
pytest -q
```

Full result: `439 passed, 2 skipped`.

## Constraints observed

- No migrations or database schema changes.
- No route/template rollout, production configuration, infrastructure, CI/CD,
  GitOps, Kubernetes, or Azure changes.
- No medical diets, autonomous dieting, or food database.
- No merge performed.

## Recommended next slice

Review the persistence model and authorization boundary, add a database adapter
with transactional overlap protection, then build a coach assignment form and
read-only athlete target panel. Only after that should legacy copied targets be
removed from check-in UX through an explicit migration/deprecation plan.
