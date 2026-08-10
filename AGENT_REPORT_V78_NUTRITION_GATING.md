# Agent B — V7.8 nutrition entitlement gating

## Delivered

- Added one service-layer nutrition entitlement policy using the existing
  `AthleteCheckinSettings.nutrition_enabled` field; no migration or billing work.
- Gated dedicated nutrition check-ins and all nutrition import mutations with
  direct-route `403` protection.
- Removed disabled athlete navigation, dashboard nutrition content, prompts and
  nutrition-derived dashboard projections.
- Removed disabled nutrition submissions from the coach review queue without
  adding per-athlete queries.
- Preserved coach-visible nutrition and import history as read-only, with active
  add/import/review controls removed.
- Persisted an explicit disabled entitlement for newly created athletes and kept
  a missing-row compatibility fallback for legacy clients.
- Added focused Python and Playwright coverage.

## Data and product decisions

No historical data is deleted or modified when entitlement changes. Existing
coach reporting remains available because product policy requested historical
visibility where appropriate. The MyFitnessPal disconnect operation retains its
pre-existing destructive semantics only while nutrition is enabled; disablement
cannot invoke it.

Meal-plan and macro-prescription modules are currently schema-independent domain
libraries with no active routes or task/reminder generation, so there was no
runtime surface to gate.

## Verification

Run from `platform-portal`:

```text
pytest -q tests/test_nutrition_entitlements.py tests/test_athletes_nutrition.py tests/test_athlete_dashboard.py tests/test_coach_dashboard.py tests/test_nutrition_import.py tests/test_checkins.py
```

The focused Playwright case is in `e2e/tests/coach.spec.ts` and requires the
repository's normal seeded E2E server/browser environment.

Result: `470 passed, 2 skipped`. The focused Playwright command could not run in
this checkout because the `playwright` executable is not installed
(`sh: playwright: not found`); the test was added but is not claimed as executed.
