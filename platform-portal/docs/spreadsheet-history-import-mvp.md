# Spreadsheet history import MVP

The MVP imports coach-approved, completed historical work into the canonical
`TrainingSessionLog` and `TrainingSetResult` history. It never creates or edits
a `TrainingBlock`, prescription, live programme, or athlete-state fact.

## Supported shapes

- UTF-8 CSV and macro-free XLSX, with columns in any order.
- A header within the first 30 rows, blank/structural rows, and carried-down
  dates/week/session labels where a session value appears only on its first row.
- One row per performed set, one row per exercise with a `Sets` count, and
  `3x5`/`3×5` in either the Sets or Reps column.
- Sheets named for an athlete, week, or block are inspectable. The MVP safely
  selects the sheet with the strongest recognized header; it imports one sheet
  per wizard run and does not infer meaning from the sheet name.

Exercise and an unambiguous training date are required for persistence. Sets
defaults to one; all other fields are optional. Missing values do not produce
inferred load, RPE, readiness, fatigue, injury, weakness, or programming state.

## Deliberately unsupported

- Multi-table sheets, horizontal calendars, exercises encoded only by cell
  position or formatting, and multiple athletes mixed in one sheet.
- Merged-cell semantics, hidden-sheet semantics, charts, images, macros,
  password-protected files, legacy `.xls`, Google Sheets URLs, and HTML.
- Formula or cached formula values. Formula cells are blanked and warned about.
- Automatic unit conversion, loose athlete-name attachment, or live programme
  reconstruction.

## Mid-block resume follow-up

Safe reconstruction needs a separate preview-only proposal model containing
source batch, candidate block/week/session grouping, unresolved exercise and
prescription semantics, and an explicit coach decision per ambiguity. A later
commit would create a draft (never active) `TrainingBlock` through the existing
programming authoring service and record a programme revision identifying the
approved proposal. It must not derive prescribed work from performed sets or
activate a programme. This branch intentionally stops at completed history.
