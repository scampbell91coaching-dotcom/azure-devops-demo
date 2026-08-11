# Agent report: guided client onboarding

## Scope

Implemented in the isolated `agent/client-onboarding-20260811-015941` worktree from base `7d77bdc`. No merge, deployment, billing integration, or migration was performed. No migration file or migration number was created.

## Outcome

Added a coach-only guided workflow at `/athletes/<athlete_id>/onboarding`:

1. issue the existing secure account invitation;
2. wait for the athlete to activate the existing account token;
3. capture a primary goal and definition of success;
4. confirm existing client-service entitlements;
5. publish an existing draft programme, or skip this requirement when training coaching is not included;
6. configure entitled weekly check-in modules and the check-in day;
7. show a derived ready state.

Athlete creation now redirects to the guided workflow. The existing athlete dashboard also links back to it.

The server enforces step order; hiding later forms is not the only guard. Invalid or out-of-order mutations fail without persisting partial onboarding data.

## Foundations reused

- `AccountToken` and `account_lifecycle` for invitation delivery and account activation.
- Append-only `ClientServiceChange` records for service access.
- Existing `TrainingBlock` publication rules, including active-programme conflict protection.
- Existing `AthleteCheckinSettings` for weekly modules and schedule.
- Append-only `AthleteStateFact` records for explicit goals and the two configuration acknowledgements needed to distinguish guided completion from legacy defaults.

Onboarding state is derived from those records on every request. There is no parallel onboarding table or mutable progress counter.

## Main files

- `platform-portal/portal/services/client_onboarding.py`: ordered state projection and current-step guard.
- `platform-portal/portal/athletes.py`: coach-only onboarding routes and mutations.
- `platform-portal/templates/athletes/onboarding.html`: guided server-rendered experience.
- `platform-portal/static/css/client_onboarding.css`: responsive progress and form layout.
- `platform-portal/tests/test_client_onboarding.py`: authorization/order, full invite-to-ready flow, persisted outcomes, and non-training programme skip.

## Verification

- Focused onboarding and adjacent regression suite: `21 passed`.
- Full `platform-portal/tests` suite: `527 passed, 2 skipped, 2 failed`.
- `git diff --check`: passed.
- Migration diff: empty.

The two full-suite failures are deterministic base behavior in `test_v79_authorization_boundaries.py`: athlete-owned nutrition-import preview and commit return `400`/`404`, while that test expects `403`. The base authorization allow-list explicitly permits those athlete nutrition-import endpoints, and this work does not modify `portal/auth.py` or nutrition-import authorization.

## Operational notes

- Invitation delivery continues to use the configured transactional-email transport and existing 48-hour lifetime.
- The workflow changes access only; it does not create charges or call a billing system.
- Publishing still refuses to replace an already-active programme.
- Historical programme, entitlement, goal, and check-in records are retained.
