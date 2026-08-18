# Accessory intelligence

Block Factory reuses the canonical `exercises` catalogue. It does not maintain
a second accessory model. Existing fields supply identity, display name,
movement/category, muscle emphasis, equipment, fatigue, prescription defaults,
progression/regression, constraint tags and active state.

V7.2 adds only selection-specific metadata:

- `auto_select`: a hard, reviewed opt-in for automatic planning; legacy and
  coach-maintained rows default to false.
- `lift_relevance`: JSON list containing `squat`, `bench`, `deadlift`, or `all`.
- `training_phases`: JSON list of Block Factory goals, or `all`.
- `compatibility_tags`: exact contextual tags for repository/service callers.
- `coach_priority`: descending deterministic selection priority.

## Selection contract

Automatic planning considers only active rows with both `accessory_suitable`
and `auto_select` true. The production export sets that flag through a reviewed
safe-category allowlist; it never enables every accessory row. The read-only
catalogue audit reports a specific not-ready explanation when this pool is
empty.

The service applies phase, lift, equipment, exact constraint tags and a
conservative structured powerlifting constraint backstop. It orders by coach
priority, Athlete State evidence, recovery suitability, fatigue and stable
catalogue identity. Session ledgers account for main-lift exposures, next-day
S/B/D work, compound class and local fatigue.

Volume is deterministic first-week accessory work: Low allows 2 weekly sets
per training day and at most one movement per day on average; Moderate allows
4 sets and 1.5 movements per day; High allows 6 sets and 2 movements per day.
All levels also have equal fatigue-unit ceilings and per-session recovery
limits. Reduced readiness scales both weekly set/fatigue budgets and movement
count, then lowers sets and RPE. A meet-bound/peaking block uses 55% of those
budgets and excludes fatigue-4/5 assistance.

Manual pinned exercises replace all automatic suggestions and remain
authoritative even when a structured conflict requires a coach warning. Every
pin receives week-specific sets, reps, RPE and rest; supplied coach dose fields
are preserved and missing fields receive purpose-specific defaults. Selecting “No
assistance” intentionally produces none. Automatic mode produces zero only when
no unused active, accessory-suitable candidate meets the phase, lift,
compatibility, constraint and fatigue-budget filters. Preview outcome metadata
distinguishes that case from intentional none and coach-pinned replacement. No
athlete-state diagnosis or probabilistic/LLM selection is performed.
