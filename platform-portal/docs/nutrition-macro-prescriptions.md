# Nutrition macro prescriptions

Nutrition macro prescriptions are immutable coach decisions, not calculated diet advice. A prescription records daily calories, protein, carbohydrate and fat; optional fibre, meal count, coach notes, and complete training/rest-day variants; and an inclusive effective date range.

Only a coach can create a prescription, and only while nutrition coaching is currently enabled for the athlete. An athlete with that entitlement can read the prescription effective today at `/athlete/nutrition-targets`. Disabling nutrition removes current athlete access and blocks new assignments, while the coach can still read all historical versions.

Rows are append-only. Corrections are made by adding a new, non-overlapping effective version. PostgreSQL uses a GiST exclusion constraint to prevent overlapping athlete date ranges under concurrent transactions; SQLite uses an equivalent insert trigger. Both databases reject updates and deletes. Check-ins, imported intake, adherence, bodyweight and other observations never update or resolve prescription truth.

This feature does not generate targets, recommend dieting strategies, or provide medical-diet logic. A human coach supplies every value and note.
