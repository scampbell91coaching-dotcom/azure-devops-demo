# Traditional Strength exercise catalogue

The bundled catalogue is generated from
`scripts/build_exercise_catalogue.py`. Its coaching text is concise, original
material intended for programming support; it does not make treatment claims.

## Coverage audit

The version 3 baseline contained 276 exercises: 30 squat, 30 bench, 30
deadlift, 146 accessory and 40 warm-up records. It had strong competition-lift,
bodybuilding, unilateral and trunk coverage, but no explicit conditioning,
strongman, GPP, rehabilitation-regression, upper-back or lower-back families.

Version 4 contains 342 exercises:

| Movement | Records |
| --- | ---: |
| Squat | 30 |
| Bench | 30 |
| Deadlift | 30 |
| Accessory | 200 |
| Warm-up | 52 |

The accessory movement includes 140 general accessories, 22 regressions, 22
unilateral exercises, 12 strongman fundamentals, 10 GPP exercises, eight
conditioning options and one advanced lift. Warm-ups now include breathing and
positional drills, wrist and upper-body mobility, and additional ankle, hip and
lower-body preparation.

## Import and coach-data ownership

Canonical names and aliases share a case- and punctuation-insensitive identity.
This prevents catalogue records and coach-created exercises from duplicating one
another under common abbreviations or spelling variants. Repeating an import is
idempotent.

A null `catalogue_version` marks a coach-maintained row. Imports use these rows
for duplicate detection but never update their fields. New coach exercises have
a null version, and editing a catalogue exercise through the exercise library
transfers the complete row to coach ownership by clearing its catalogue version.
This preserves Block Factory compatibility because exercise IDs and the existing
movement/category fields remain unchanged.

Search is case-insensitive, punctuation-tolerant and requires every entered term
to match the exercise's name, aliases, family, category, muscles, equipment or
goal. Filters and results include active exercises only.
