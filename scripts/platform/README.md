# Platform Operations Toolkit

Scripts:

- `azure-inventory` — sanitized, read-only Azure subscription metadata inventory ([documentation](../../docs/azure-inventory.md))
- `platform-health.sh`
- `validate-platform.sh`
- `check-drift.sh`
- `cleanup-repo.sh`
- `run-platform-toolkit.sh`
- `keepass-bootstrap.sh`, `keepass-validate.sh`, and `keepass-backup.sh`
- `check-no-keepass-files.sh` (CI guard against tracked KeePass data)

See [KeePass operations](../../docs/keepass-operations.md) for the security
boundaries and exact usage.

Install into the repository:

```bash
mkdir -p ~/azure-devops-demo/scripts/platform
cp *.sh ~/azure-devops-demo/scripts/platform/
chmod +x ~/azure-devops-demo/scripts/platform/*.sh
```

Run one tool at a time and review its output before committing changes.
