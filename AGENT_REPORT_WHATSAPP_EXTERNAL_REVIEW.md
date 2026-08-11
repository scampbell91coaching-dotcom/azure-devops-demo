# WhatsApp external coaching review prototype

## Outcome

Implemented a coach-only Traditional Strength record of coaching reviews that
happened over WhatsApp. The athlete dashboard now lets a coach record and view:

- athlete and fixed `channel=whatsapp` provenance;
- review date and time;
- optional links to an existing training session log, set result, technical
  observation, and external HTTP(S) URL;
- coach summary and action;
- follow-up-required and resolved states.

Open records can subsequently be marked resolved. Reviews are ordered by review
time and then ID, newest first.

## Explicit external-integration boundary

This is an outcome-recording prototype, not a WhatsApp integration. It has no
WhatsApp API/client, webhook, message send/receive behavior, contact or provider
identifiers, message-body persistence, uploads, downloads, or media storage.
The optional URL is stored and rendered as an external reference only; the
application never fetches it. The channel is set server-side and constrained in
the database, so form input cannot select or forge another channel.

## Authorization and integrity

Both mutations require an authenticated coach role. Existing platform
authorization keeps athlete accounts off the coach dashboard, and the routes
also reject athlete-role writes with `403`.

Every optional internal reference is checked against the athlete in the route.
Cross-athlete or missing references return `404`; a selected set must belong to
the selected session when both are supplied. External URLs accept only absolute
HTTP(S) values. Review time, summary, and action are required.

## Schema decision

The Alembic file is
`migrations/versions/whatsapp_external_review_prototype.py`, with revision ID
`whatsapp_external_review` and parent `0015_client_services`. It intentionally
does not reserve or consume `0016` (or any other numeric migration slot).

## Verification

Targeted feature and migration verification:

```text
pytest -q tests/test_external_coaching_reviews.py tests/test_database_migrations.py
13 passed, 1 skipped
```

Full portal suite:

```text
pytest -q
528 passed, 2 skipped, 2 failed
```

The two failures are existing nutrition-import authorization expectations in
`tests/test_v79_authorization_boundaries.py`: preview returns `400` and commit
returns `404`, while that test expects `403`. Both reproduce when that existing
parametrized test is run alone and neither request reaches an external-review
route. No unrelated nutrition behavior was changed.

## Files changed

- `platform-portal/portal/models/external_coaching_review.py`
- `platform-portal/portal/models/__init__.py`
- `platform-portal/portal/external_reviews.py`
- `platform-portal/portal/__init__.py`
- `platform-portal/portal/athletes.py`
- `platform-portal/templates/athletes/dashboard.html`
- `platform-portal/migrations/versions/whatsapp_external_review_prototype.py`
- `platform-portal/tests/test_external_coaching_reviews.py`
- `platform-portal/tests/test_database_migrations.py`
- `AGENT_REPORT_WHATSAPP_EXTERNAL_REVIEW.md`

No infrastructure, deployment, merge, or external service was touched.
