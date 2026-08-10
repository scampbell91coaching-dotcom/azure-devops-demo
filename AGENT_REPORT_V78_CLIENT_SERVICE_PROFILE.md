# Agent report: V7.8 client service profile

## Outcome

Implemented a small, persistence-independent entitlement domain and focused
tests. No migration or access-control route changes were made. This leaves a
clean seam for durable storage without treating billing or weekly check-in
settings as product access.

## Changes

- Added `platform-portal/portal/services/client_service_profiles.py` with:
  - independent training, nutrition and meet-day entitlements;
  - `none`/`limited`/`included` video review;
  - half-open effective periods;
  - partial, dated and auditable coach overrides;
  - provenance values, including a distinguishable legacy fallback;
  - repository protocol and effective-profile resolver;
  - a current/new-activity decision that does not gate historical reads.
- Added `platform-portal/tests/test_client_service_profiles.py` covering all four
  training/nutrition combinations, compatibility defaults, date boundaries,
  overrides, superseding revisions, historical-read intent and validation.
- Added `docs/v7.8-client-service-profile.md` with model findings, semantics,
  defaults, integration guidance and deferred migration requirements.

## Key decisions

- Did not reuse `AthleteCheckinSettings`: those booleans configure a check-in
  form and have different current defaults/meaning.
- Did not add fields to `Athlete`: effective history and overrides require
  append-only records, not mutable current-state columns.
- Existing athletes without a record resolve to training, nutrition and
  meet-day enabled; video review resolves to none. This preserves current
  behavior while making fallback provenance visible.
- Disabling affects new/current service actions only. Stored programming,
  check-in, nutrition and meet-day data remains readable.

## Verification

`cd platform-portal && pytest -q tests/test_client_service_profiles.py`

Result: `10 passed`.

## Follow-up required

Implement and migrate append-only profile/override tables, backfill explicit
legacy profiles, add a SQLAlchemy repository, then integrate entitlement checks
at mutation/current-workflow boundaries. Deploying route gates before durable
storage and backfill is not recommended.
