# Programming engine Wave 2 exposure semantics

New Block Factory proposals treat lift family, coaching purpose, stress role,
exercise choice, and prescription as separate values. The complete values and a
coach-facing deterministic reason are stored in the HMAC-signed proposal
preview. Acceptance does not run the exposure planner; it validates and
materializes the already-finalized signed programme graph.

The database remains unchanged. `ProgrammingLiftSlot.exposure_role` is a legacy
compatibility projection selected during preview. It allows existing programme
rendering and revision/history readers to continue loading `competition`,
`primary_volume`, `secondary_strength`, `technique`, `low_fatigue`, and
`overload`. New coaching decisions never read that projection. The full purpose
and stress semantics remain on the retained signed proposal, while the concise
reason is also materialized as the main-lift prescription note.

For five or six weekly bench exposures, exactly two are hard Competition Bench:
one `competition_intensity` and one `competition_volume`. Every other bench
exposure is explicitly `lower_stress`. A second squat or deadlift always has an
explicit secondary purpose, and the planner rejects more than two deadlift
exposures.
