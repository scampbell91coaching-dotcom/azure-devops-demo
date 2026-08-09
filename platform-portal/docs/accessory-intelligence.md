# Accessory intelligence

Block Factory reuses the canonical `exercises` catalogue. It does not maintain
a second accessory model. Existing fields supply identity, display name,
movement/category, muscle emphasis, equipment, fatigue, prescription defaults,
progression/regression, constraint tags and active state.

V7.2 adds only selection-specific metadata:

- `auto_select`: explicit coach opt-in; legacy rows default to false.
- `lift_relevance`: JSON list containing `squat`, `bench`, `deadlift`, or `all`.
- `training_phases`: JSON list of Block Factory goals, or `all`.
- `compatibility_tags`: exact contextual tags for repository/service callers.
- `coach_priority`: descending deterministic selection priority.

## Selection contract

The repository returns only active, accessory-suitable, coach-enabled rows.
The service applies exact phase, lift, compatibility and excluded constraint
tags. It orders by coach priority, then lower fatigue cost, then exercise name.
Block Factory requests no more than one unused candidate per day and includes
the matching metadata, priority and fatigue in its explanation.

Manual pinned exercises replace all automatic suggestions. Selecting “No
assistance” produces none. If no exercises have `auto_select=true`, output is
identical to V7.1: no accessories are generated unless the coach pins them.
No athlete-state diagnosis or probabilistic/LLM selection is performed.
