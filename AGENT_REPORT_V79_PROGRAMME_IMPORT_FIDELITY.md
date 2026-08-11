# V7.9 Programme Import Fidelity — agent report

## Outcome

**Verdict: programme-import fidelity is not established.** There is no programme importer, supported source format, or programme corpus/fixture in the repository. Block Factory is the nearest structured ingestion path and it demonstrably drops accepted coaching metadata when turning a proposal into programme rows.

The full evidence and requested-field matrix are in `docs/v7.9-programme-import-fidelity.md`.

## Highest-risk findings

1. No source-to-destination contract or loss report exists, so an external programme import claim is currently untestable.
2. Factory acceptance drops meet date, goal/split, lift-frequency intent, deadlift grip/strap settings, accessory policy, and proposal provenance.
3. Accessory names/count/order survive, but role and selection reasons do not.
4. Factory-generated rows contain sets/reps/RPE only; tempo, rest, RPE caps and load modes are absent despite destination fields existing.
5. Pairings/supersets, programme-specific equipment constraints, substitutions and competition linkage have no structured destination representation.

## Focused fix

Programme duplication previously dropped persisted warm-up assignments and overrides. A small copy service now preserves authored preparation intent across session, week and block copy paths while excluding resolved athlete snapshots. The regression proves protocol reason plus drill sets/reps/rest/cue/reason survive and historical snapshots do not.

No general importer or schema expansion was attempted without a real, coach-approved source corpus.

## Verification

`pytest -q tests/test_session_lifecycle.py tests/test_week_lifecycle.py tests/test_programming_core.py` — **24 passed**.

