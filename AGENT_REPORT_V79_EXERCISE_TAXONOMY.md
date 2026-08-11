# V7.9 Exercise Taxonomy agent report

## Outcome

Audited all requested taxonomy dimensions across the 342-record production
catalogue and its Block Factory, accessory, swap, warm-up and athlete-state
consumers.

The catalogue is sufficient for browsing/manual selection and conservative
swaps, but not for autonomous Block Factory selection, warm-up recommendation,
or movement-need/athlete-constraint matching. Existing columns are sufficient
for a reviewed next catalogue version, so no migration was added.

## Delivered

- `docs/v7.9-exercise-taxonomy-audit.md`: coverage matrix, consumer audit,
  inconsistencies, duplicated concepts, safety boundary and sequenced backlog.
- Safe catalogue correction: Kickstand Romanian Deadlift now carries the
  established `unilateral` constraint tag, aligning all 22 unilateral-category
  records with that tag.
- Regression coverage for generated-asset synchronisation, unilateral metadata
  consistency and canonical competition-root relationships.

## Key evidence

- Production seed: 342 records (30 squat, 30 bench, 30 deadlift, 200 accessory,
  52 warm-up); no canonical-name/alias identity collision.
- All seeded records omit automatic-selection, lift-relevance, phase and
  compatibility metadata. Consequently, production imports yield zero seeded
  automatic accessory candidates until a coach explicitly enables records.
- Fatigue is class-bucketed rather than exercise-sensitive: 52 at 1, 200 at 2,
  87 at 4 and 3 at 5.
- 164 equipment options contain unsplit alternatives; 64 accessories have a
  composite movement pattern.
- Warm-up records and the warm-up protocol domain are not linked.
- Athlete constraints/technical observations are free text and have no safe,
  explicit translation to catalogue properties/purposes.

## Safety decisions

No record was automatically enabled. No migration, clinical inference, fuzzy
constraint matching, progression edge, grip meaning or strap compatibility was
introduced without domain evidence.

## Verification

Run:

```bash
cd platform-portal
pytest -q tests/test_exercise_taxonomy.py tests/test_exercise_knowledge_import.py tests/test_accessory_intelligence.py tests/test_exercise_swaps.py
```
