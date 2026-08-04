# Release-readiness dashboard

`/release-readiness` displays the existing repository release-gate evidence at
`evidence/release/release-evidence.json`. The request handler only reads and
validates that fixed repository-relative file; it never generates evidence or
runs release commands. The producer remains the sole source of gate logic.

Missing, unreadable, unsupported, malformed, future-dated, or evidence older
than 24 hours is shown as
`NOT_READY` with no evidence details. Generate fresh evidence separately using
the documented release tooling, then reload the page.
