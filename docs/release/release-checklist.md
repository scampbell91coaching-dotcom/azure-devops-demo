# Release checklist

- [ ] Generated evidence status is `ready` for the intended commit.
- [ ] The commit and branch in evidence match the release candidate.
- [ ] Any dirty worktree state is understood and excluded from the release.
- [ ] PostgreSQL evidence is present when the release changes database behavior.
- [ ] Migration heads have been reviewed and there is exactly one intended head.
- [ ] Helm and Terraform results have been reviewed.
- [ ] The rollback plan is current and has an owner.
- [ ] Normal change approval has been recorded outside this repository.
