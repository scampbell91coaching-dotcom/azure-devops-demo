# V7.9 Programme Corpus Analysis report

## Outcome

Completed a repository-wide programme-data inventory and added a golden corpus
fixture/test without modifying Block Factory production selection code.

The central finding is material: this repository has no imported real-programme
corpus. The bundled “intelligence” data is an exercise catalogue, while the
programme-shaped records are static templates and synthetic test/E2E seeds.
Accordingly, no honest analysis can claim real-programme parity or evidence for
sessions above three accessories.

## Results

- Canonical maintained sample: 10 non-duplicated sessions.
- Accessories/session: 8 × 0, 2 × 1; mean 0.2; maximum 1.
- Sessions with more than 3 accessories: none.
- Accessory exposure means: squat 0.29, bench 0.20, deadlift 0.25.
- Lift slots/session: 5 × 1, 3 × 2, 2 × 3; one secondary/back-off slot total.
- Repeated family: upper pull, twice.
- Distribution: 1 upper, 5 lower, 4 full-body under the documented convention.
- Competition-phase comparison: unavailable; source data has no comparable
  phase labels.

The evidence-based policy retains automatic Low/Medium/High at 1/2/3, requires
attributable imported sessions before reconsidering High, and explicitly
preserves manual pins/order and `No assistance = 0`.

## Files

- `docs/v7.9-programme-corpus-parity.md`
- `platform-portal/tests/fixtures/programme_corpus_parity.v1.json`
- `platform-portal/tests/test_programme_corpus_parity.py`

Production selection code was not changed.

## Verification

- `pytest -q platform-portal/tests/test_programme_corpus_parity.py platform-portal/tests/test_block_factory_v3.py platform-portal/tests/test_programming_templates.py`
  — 28 passed.
- Golden JSON parsed successfully with `python -m json.tool`.
- `git diff --check` passed.
