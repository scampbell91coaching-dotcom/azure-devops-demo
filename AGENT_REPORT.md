# Nutrition Macro Delivery — V7.9

## Delivered

- Append-only `nutrition_macro_prescriptions` persistence and SQLAlchemy/domain adapter.
- Single-head Alembic revision `0016_nutrition_macros`, with transactional overlap protection.
- Coach assignment, current-prescription and history browser UI.
- Athlete current-target UI with daily, training/rest variants, meal count and coach notes.
- Coach/athlete authorization and current nutrition-entitlement gates; coach history survives disable.
- Tests covering authorization, overlap, dates, variants, entitlement and rendered browser behavior.
- Product/domain documentation explicitly separating prescription truth from intake/check-ins and excluding autonomous or medical dieting logic.

## Verification

- Full portal suite: `494 passed, 2 skipped`.
- Final focused migration/browser suite: `6 passed`.
- Alembic: one head, `0016_nutrition_macros`.
- Python byte-compilation and `git diff --check`: passed.

## Commit status

The implementation is ready in the working tree, but the managed workspace exposes the shared Git administrative directory read-only. `git add`/`git commit` could not create `/home/steve/azure-devops-demo/.git/worktrees/v79-macro-delivery-20260810-221810/index.lock`. No implementation or verification work remains; the tree can be committed once that Git directory is writable.
