# Agent C Report — Traditional Strength V7.2 Coaching Rules

## Outcome

Implemented the first deterministic, explainable coaching recommendation rules engine using the existing athlete-state tables. No migrations or automatic programming mutations were added.

## Implementation

- Added `portal/services/coaching_rules.py`.
- Defined rules as immutable data (`ObservationRule` and `ConstraintRule`) so thresholds, phrases, priorities, recommendations, and non-claims are directly testable.
- Added a small demonstrative rule set:
  - repeated squat hip-shift observations (2 occurrences in 28 days);
  - repeated squat heel-pressure observations (2 occurrences in 28 days);
  - active constraints that explicitly name squat, bench, or deadlift.
- Contrary observations (for example, `hip shift resolved`) prevent an ambiguous technical rule from matching.
- Candidates expose:
  - rule identifier and generator version;
  - matched conditions;
  - exact source observation/constraint references and relevant recorded values;
  - confidence and numeric priority;
  - recommendation;
  - explicit statement of what the rule is not claiming;
  - coach-authority and no-programming-mutation declarations.
- Candidate ordering is deterministic: descending priority, then rule identifier, then source IDs.
- Candidates can be persisted as `proposed` with the existing `AthleteStateRecommendation` model.
- Coaches can accept, reject with a reason, or override with a reason and replacement guidance. Overrides use the existing `AthleteStateOverride` model and are surfaced on subsequent evaluations.

## Safety boundaries

- Recommendations are candidates only.
- No programming is changed or accepted implicitly.
- No medical diagnosis, injury cause, physiotherapy prescription, or exercise suitability is inferred.
- Conflicting evidence is not resolved by guessing.

## Tests

Added `platform-portal/tests/test_coaching_rules.py`, covering:

- match and non-match behavior;
- repeated-observation thresholds and date windows;
- wrong-lift exclusions;
- conflicting/contrary observations;
- active, resolved, and generic constraints;
- complete provenance and non-claim fields;
- deterministic ordering and repeat evaluation;
- persistence as a proposed candidate;
- acceptance, rejection, and override behavior;
- required reasons/replacement guidance for coach decisions.

Verification:

```text
Focused athlete-state/rules suite: 12 passed
Final coaching-rules suite:       8 passed
Full platform-portal suite:       410 passed, 2 skipped
compileall:                       passed
git diff --check:                 passed
```

Ruff was not installed in the supplied environment, so its executable checks could not be run. Files were manually kept within the repository's formatting conventions and checked for lines over 100 characters.

## Schema and scope

- No migration added.
- No model/schema change added.
- No route or UI mutation added.
- Existing athlete-state persistence was reused.

## Commit status

The logical implementation commit was prepared as:

```text
feat(coaching): add explainable deterministic rules engine
```

The commit could not be created because this sandbox allows writes to the worktree but Git's real administrative directory is outside it and read-only:

```text
fatal: Unable to create '/home/steve/azure-devops-demo/.git/worktrees/v72-coaching-rules-20260809-171331/index.lock': Read-only file system
```

The requested `~/AGENT_REPORT_RULES.md` location is also outside the writable sandbox. This report is therefore stored as `AGENT_REPORT_RULES.md` at the worktree root.
