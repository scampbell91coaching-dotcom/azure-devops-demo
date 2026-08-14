# Canonical tenancy reconciliation

`reconcile-canonical-tenancy` audits legacy data that predates canonical
`OrganisationMembership` and `CoachAthleteOwnership` records. It is an
operational repair tool, not a migration: it does not change schema or
`alembic_version`.

## Safety boundary

The command repairs only the explicit single-coach/single-organisation legacy
case: exactly one active organisation and exactly one active global coach user.
In that case it can create an active owner membership for that coach and active
ownership rows for otherwise unowned athletes. It never selects a record by ID,
email, name, or another heuristic.

The command refuses when there is no organisation, multiple or inactive
organisations, more or fewer than one active coach, an inactive membership or
ownership, or an existing ownership assigned inconsistently. Refusal output
describes the state that an operator must resolve through an approved lifecycle
or tenant assignment process. Inactive rows are deliberately left inactive.

## Operator procedure

Run against the intended environment using its normal protected database
configuration. Do not point the command at production without a separately
approved production change procedure.

First capture the default read-only report:

```console
flask --app app reconcile-canonical-tenancy
```

Review `organisation_id`, `coach_user_id`, `missing_membership`, and
`missing_ownership_athlete_ids`. A `refused` status exits non-zero and must not
be bypassed. A `healthy` status needs no action. A `changes-required` status is
eligible for the safe bootstrap only after the listed identities and athletes
have been checked against the approved operational record.

Apply the exact reported repair explicitly:

```console
flask --app app reconcile-canonical-tenancy --apply
```

The membership and all missing ownerships are committed together. A database
error rolls the transaction back. Immediately repeat the dry-run command and
retain both JSON reports with the change record; the follow-up status should be
`healthy`. Repeating either dry-run or apply is idempotent.

For an ambiguous or inactive state, do not delete records, rewrite lifecycle
status, or edit `alembic_version`. Establish the intended organisation and
coach/athlete assignments through the authorised business process, then rerun
the dry-run audit.
