# Programming engine Wave 0 characterization

Wave 0 adds a safety harness only. It does not redesign coaching behaviour,
scheduling, exposures, variation selection, accessories, RPE, or volume ownership.

## Active paths

- Preview enters at `POST /programming/factory/preview` (`block_factory.preview`). It
  parses `FactoryRequest`, calls `_preview`, weekly programming intelligence, and
  proposal explanations, then stores the entire signed proposal payload.
- Acceptance enters at `POST /programming/factory` (`block_factory.generate`). It
  loads the stored proposal, checks athlete access, HMAC, version, and source
  freshness, validates the signed persistable graph, and materializes that graph
  directly before the atomic status transition.
- Integrity is a SHA-256 HMAC over canonical JSON using the application secret.
  Status transition from `proposed` supplies replay protection.
- Wave 0 originally characterized acceptance-time regeneration and the resulting
  graph mismatch. Wave 1 closes that mismatch: weekly set allocation and effective
  RPE are finalized before signing, and acceptance performs no coaching decisions.

## Decision ownership still present

`_day_sequence`, `_VARIATIONS`, `_PRESCRIPTIONS`, `_week_rpe`,
`_allocate_weekly_sets`, `WeeklyProgrammingIntelligence`,
`VolumeProgressionService`, and accessory planning/intelligence all participate in
decisions today. Wave 0 deliberately does not consolidate these owners.

## Safety harness

`tests/programming_graph.py` normalizes proposal and persisted graphs without
database IDs. `test_programming_wave0_characterization.py` locks deterministic
preview structure, acceptance ordering/provenance/status/revision snapshots,
asserts exact signed/persisted graph parity, reads every historical exposure role,
and protects completed athlete results and accepted historical blocks. Existing
focused suites additionally lock HMAC tampering, staleness, replay, coach-selected
accessories, lift slots, warm-up assignment persistence, and revision immutability.

No schema field or migration is required by this harness.
