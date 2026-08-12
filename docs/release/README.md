# Release readiness

Release evidence is generated locally by `scripts/release/release-evidence`.
It is a validation tool, not a deployment tool. Review the JSON evidence and
Markdown report together with the checklist and rollback plan before approval.

See `scripts/release/README.md` for options, exit codes, and examples.

Product test selection, ordered Playwright smoke and the relationship between
browser regression and release evidence are defined in the
[powerlifting regression matrix](pl-regression-matrix.md).
