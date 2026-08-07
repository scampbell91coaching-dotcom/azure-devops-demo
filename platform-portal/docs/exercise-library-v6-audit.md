# Exercise Library V6 audit

## Scope and method

The bundled 342-record catalogue, model, importer, coach-owned row behaviour,
migrations, search and Block Factory integration were inspected. Identity
matching normalises case, punctuation and Unicode and includes aliases. The
catalogue builder rejects collisions before emitting JSON. Similar names were
also reviewed as pairs; the flagged pairs (for example paused/long-pause bench,
Romanian/cable Romanian deadlift and Nordic/assisted Nordic curl) represent
different setups or purposes, not confirmed duplicates.

No Block Factory algorithm, prescription, existing coach UI or coach-authored
row is changed by V6. There is no concept of an accessory day or quota here.

## Findings

- No exact canonical/alias identity collision exists in the bundled catalogue.
- Naming is mostly consistent title case with hyphenated compound modifiers.
  `Pause Squat` versus `Paused Bench Press` is a stylistic inconsistency, but a
  rename was not justified because prescriptions persist exercise names as
  text. `Duffalo-Bar Squat` and `Cambered-Bar Squat` share an equipment value
  but are not treated as duplicates without stronger source evidence.
- The five primary movement values are valid and balanced: 30 squat, 30 bench,
  30 deadlift, 200 accessory and 52 warm-up records.
- Existing `family` mixes lift families, muscle/region groupings and warm-up
  purposes (40 values). It remains untouched for compatibility. V6 separates
  powerlift family from movement pattern.
- Existing `category` has 10 valid values, but it combines relationship
  (`variation`, `regression`), use (`accessory`, `conditioning`) and sport
  (`strongman`). V6 does not reinterpret it; `specificity` and
  `technical_purposes` carry the swap-relevant meaning explicitly.
- Competition relationships previously existed only as relevance text. V6
  identifies the three competition roots and links each main-lift variation to
  its root through `variation_of`.
- Fatigue metadata is internally valid but low-resolution: the three
  competition lifts are 5, all 87 other main-lift records are 4, all 200
  accessories are 2 and all warm-ups are 1. V6 preserves these values rather
  than invent exercise-by-exercise costs. Future review should separate local,
  axial and systemic fatigue with evidence.
- Accessory suitability is consistent with current scope: all accessories are
  suitable; competition/main-lift and warm-up records are not. This means
  suitability is a use flag, not a quota or a day type.
- Equipment exists on every catalogue record, but some accessory and warm-up
  values are broad alternatives. `equipment_options` initially contains the
  source statement as a single option so a future workflow cannot mistakenly
  interpret every comma-separated implement as required.
- Existing regression/progression text often describes coaching actions rather
  than canonical exercise relationships. It remains useful display knowledge,
  but must not be used as a foreign key. `variation_of` is the only canonical
  relationship added in this pass.

## V6 metadata contract

All new database columns are nullable for legacy and coach-owned exercises.
Bundled schema-version 6 records require:

| Field | Meaning |
| --- | --- |
| `lift_family` | `squat`, `bench`, `deadlift`, or `none`; independent of old `family` |
| `movement_pattern` | Explicit mechanical/programming pattern used for filtering |
| `specificity` | `competition`, `close_variation`, `general`, or `preparation` |
| `technical_purposes` | JSON list of explicit purposes, never an opaque score |
| `equipment_options` | JSON list of complete equipment options |
| `constraint_tags` | Non-diagnostic setup properties such as supported, unilateral or neutral-grip option |
| `variation_of` | Canonical competition-root name where the relationship is established |
| `swap_group` | Explainable first-pass compatibility boundary |

Constraint tags describe the exercise setup only. They do not diagnose an
injury, promise symptom relief or replace a coach/clinician decision.

## Swap foundation and limitations

`compatible_swaps` is a read-only candidate service. It requires the same swap
group, optionally enforces exact equipment options and excluded setup tags, and
orders candidates by same specificity, fatigue-distance and canonical name.
Every result includes human-readable reasons. It never changes a prescription.

The initial groups are intentionally conservative for competition-lift
families and broader for accessories. Some accessory groups contain distinct
sub-patterns because the source catalogue does not yet support a finer claim
(for example press-or-fly and hip-extension-or-abduction). Those groups require
domain review before a coach-facing swap feature is enabled. Likewise, broad
equipment statements should be decomposed through a reviewed catalogue update,
not string parsing at request time.

## Recommended follow-up

1. Domain-review the near-duplicate/name pairs and add aliases before any rename.
2. Split ambiguous accessory patterns and broad equipment alternatives using a
   reviewed evidence sheet.
3. Add canonical progression/regression edges only where both endpoints and the
   direction are confirmed.
4. Review fatigue by component and keep the scale anchors documented.
5. Trial swap explanations with coaches; keep selection explicit and never
   silently rewrite authored programming.
