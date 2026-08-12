# Powerlifting regression matrix

This is the release assurance map for Traditional Strength powerlifting. It
protects existing product behaviour without treating disabled future tenancy
contracts as evidence that isolation has shipped.

## Gate model

| Gate | Command | Required result |
| --- | --- | --- |
| Product regression | `python -m pytest -q platform-portal/tests` | Pass; classify skips and xfails |
| Ordered browser smoke | Run the specs below serially | Each stage passes before the next |
| Browser regression | `E2E_TEST_ONLY=1 npm run e2e` | Desktop and mobile pass |
| Release evidence | `make release-gate` | Expected DB head, commit and immutable image evidence pass |

The release gate is read-only and does not deploy. PostgreSQL migration tests
are additionally required for database changes. `saas-tenancy.future.spec.ts`
is excluded from the current product gate while tenancy is disabled; its
negative probes are specifications, not green release evidence.

## Product coverage

| Lane | Pytest evidence | Browser evidence |
| --- | --- | --- |
| Programming and Block Factory | `platform-portal/tests/test_programming_core.py`, `platform-portal/tests/test_programming_domain_v7.py`, `platform-portal/tests/test_programming_copilot_intent.py`, `platform-portal/tests/test_block_factory_v2.py`, `platform-portal/tests/test_block_factory_v3.py`, `platform-portal/tests/test_programme_revision_history.py`, `platform-portal/tests/test_v79_golden_programmes.py` | `e2e/tests/coach.spec.ts`, `e2e/tests/pilot-money-path.spec.ts` |
| RPE and volume | `platform-portal/tests/test_prescription_modes.py`, `platform-portal/tests/test_rpe_trajectory.py`, `platform-portal/tests/test_volume_progression.py`, `platform-portal/tests/test_programming_references.py`, `platform-portal/tests/test_programme_corpus_parity.py` | `e2e/tests/coach.spec.ts`, `e2e/tests/mobile.spec.ts` |
| Athlete state and warm-ups | `platform-portal/tests/test_athlete_state.py`, `platform-portal/tests/test_programming_athlete_state.py`, `platform-portal/tests/test_accessory_intelligence.py`, `platform-portal/tests/test_warmup_plans.py`, `platform-portal/tests/test_warmup_integration.py` | `e2e/tests/athlete-training.spec.ts` |
| Training lifecycle | `platform-portal/tests/test_athlete_dashboard.py`, `platform-portal/tests/test_athlete_training_log.py`, `platform-portal/tests/test_session_lifecycle.py`, `platform-portal/tests/test_week_lifecycle.py`, `platform-portal/tests/test_training_schedule.py` | `e2e/tests/athlete-training.spec.ts`, `e2e/tests/mobile.spec.ts` |
| Nutrition and meal plans | `platform-portal/tests/test_checkins.py`, `platform-portal/tests/test_nutrition_prescriptions.py`, `platform-portal/tests/test_nutrition_macro_delivery.py`, `platform-portal/tests/test_nutrition_import.py`, `platform-portal/tests/test_meal_plan_workflow.py`, `platform-portal/tests/test_meal_plan_ui.py` | `e2e/tests/nutrition-import.spec.ts`, `e2e/tests/meal-plan.spec.ts`, `e2e/tests/athlete-services.spec.ts` |
| Meet prep | `platform-portal/tests/test_meet_day.py`, `platform-portal/tests/test_attempt_selection.py`, `platform-portal/tests/test_plate_loading.py`, `platform-portal/tests/test_competition_bodyweight.py` | `e2e/tests/coach.spec.ts` |
| Performance | `platform-portal/tests/test_athlete_performance.py`, `platform-portal/tests/test_training_performance.py`, `platform-portal/tests/test_performance_chart_api.py`, `platform-portal/tests/test_performance_service.py`, `platform-portal/tests/test_performance_decisions.py`, `platform-portal/tests/test_performance_query_audit.py` | `e2e/tests/performance-dashboard.spec.ts`, `e2e/tests/performance-dashboard.mobile.spec.ts` |
| Coach UX | `platform-portal/tests/test_coach_dashboard.py`, `platform-portal/tests/test_coach_workspace.py`, `platform-portal/tests/test_design_system.py`, `platform-portal/tests/test_application_polish.py` | `e2e/tests/coach-desktop-ux.spec.ts` |
| Observability | `platform-portal/tests/test_observability.py`, `platform-portal/tests/test_platform_status_collector.py`, `platform-portal/tests/test_platform_status_manifests.py` | `e2e/tests/observability.spec.ts` |
| Release and isolation | `platform-portal/tests/test_database_migrations.py`, `platform-portal/tests/test_cross_tenant_security.py`, `scripts/release/tests/test_release_evidence.py`, `scripts/release/tests/test_pl_regression_matrix.py`, `scripts/migrations/tests/test_saas_tenancy_verify.py`, `scripts/gitops/tests/test_promote_image.py`, `tests/test_e2e_security.py`, `tests/test_e2e_seed_database.py` | `e2e/tests/auth.spec.ts`, `e2e/tests/saas-tenancy.future.spec.ts` |

## Ordered Playwright smoke

1. `e2e/tests/auth.spec.ts`
2. `e2e/tests/coach.spec.ts`
3. `e2e/tests/athlete-training.spec.ts`
4. `e2e/tests/meal-plan.spec.ts`
5. `e2e/tests/performance-dashboard.spec.ts`
6. `e2e/tests/observability.spec.ts`
7. `e2e/tests/mobile.spec.ts`

The complete browser regression remains authoritative after this smoke. Record
every intentionally skipped lane and its reason in the evidence review.
