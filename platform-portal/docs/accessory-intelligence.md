# Accessory intelligence

Block Factory reuses the canonical `exercises` catalogue. It does not maintain
a second accessory model. Existing fields supply identity, display name,
movement/category, muscle emphasis, equipment, fatigue, prescription defaults,
progression/regression, constraint tags and active state.

V7.2 adds only selection-specific metadata:

- `auto_select`: coach preference signal; preferred eligible rows rank before
  fallback rows, and legacy rows default to false.
- `lift_relevance`: JSON list containing `squat`, `bench`, `deadlift`, or `all`.
- `training_phases`: JSON list of Block Factory goals, or `all`.
- `compatibility_tags`: exact contextual tags for repository/service callers.
- `coach_priority`: descending deterministic selection priority.

## Selection contract

The repository returns active, accessory-suitable rows, with `auto_select=true`
rows ranked first as coach preferences. When no preferred row survives the
service filters, other eligible accessory-suitable rows are deterministic
fallback candidates.
The service applies exact phase, lift, compatibility and excluded constraint
tags. It orders by coach priority, then lower fatigue cost, then exercise name.
Block Factory fills a per-day fatigue budget and includes matching metadata,
priority and fatigue in its explanation. Low, Medium and High are fatigue-unit
budgets, never exercise-count ceilings.

Manual pinned exercises replace all automatic suggestions. Selecting “No
assistance” intentionally produces none. Automatic mode produces zero only when
no unused active, accessory-suitable candidate meets the phase, lift,
compatibility, constraint and fatigue-budget filters. Preview outcome metadata
distinguishes that case from intentional none and coach-pinned replacement. No
athlete-state diagnosis or probabilistic/LLM selection is performed.
