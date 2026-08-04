# KeePass operations

These repository-owned helpers finish the structure of an **existing** KeePass
database. They support the older `keepassxc-cli` interface installed for this
platform: the master password is read silently from `/dev/tty` and passed on
standard input. It is never accepted as an argument or environment variable.

## Prerequisites and usage

These scripts support GNU/Linux and require Bash plus GNU coreutils behavior;
stock macOS/BSD tools are not supported. Install `keepassxc-cli`, close
KeePassXC (to avoid concurrent writes), and keep the `.kdbx` outside this
repository. Bootstrap is the only database-writing
operation; it creates missing groups and a non-secret recovery metadata entry:

```bash
scripts/platform/keepass-bootstrap.sh /absolute/path/traditional-strength.kdbx
scripts/platform/keepass-validate.sh /absolute/path/traditional-strength.kdbx
```

Both commands prompt on the controlling terminal. Validation discards all
entry output and reports names/status only. Bootstrap is idempotent and does
not import, request, or generate operational secret values.

Backups are offline file copies and require both paths explicitly. The parent
directory must already exist, and no path inside this Git repository is
accepted. An existing destination is replaced only after a private temporary
copy in the same directory passes SHA-256 verification:

```bash
scripts/platform/keepass-backup.sh /path/source.kdbx /offline/path/backup.kdbx
```

The helper resolves `sha256sum` or `shasum` before copying, creates the
temporary copy with mode `0600`, compares source and temporary-copy SHA-256
checksums, and atomically renames the verified file. Failures remove the
temporary copy and preserve any existing destination. Its only durable output
location is the explicit destination. Store it on encrypted,
access-controlled media and test recovery.

The repository ignores `*.kdbx` and `*.kdbx.lock` as a safety net. The
`check-no-keepass-files.sh` CI guard also rejects either pattern if force-added
to Git.

## Metadata entry templates

The bootstrap creates `00 - Recovery/KeePass Database Recovery` from this
non-secret template:

```text
Database location: [absolute path outside the repository]
Backup location: [offline location]
Date created: [YYYY-MM-DD]
Emergency recovery procedure: [document and test]
Last backup test: [YYYY-MM-DD]

Purpose: KeePass database recovery information
Created: [YYYY-MM-DD]
Last verified: [YYYY-MM-DD]
Used by: Traditional Strength
Stored elsewhere: No
Rotation required: No
Owner: [named accountable owner]
```

For manually created credential metadata entries, use this notes template; do
not put the credential itself in notes:

```text
Purpose: [why this credential exists]
Created: [YYYY-MM-DD]
Last verified: [YYYY-MM-DD]
Used by: [systems or people]
Stored elsewhere: [location or No]
Rotation required: [cadence or No]
Owner: [named accountable owner]
Recovery/revocation procedure: [non-secret instructions]
```

Security boundary: these scripts do not protect a compromised host, inspect
password quality, rotate credentials, synchronize backups, or prove a backup
can be opened. Never commit databases, backups, terminal captures, or secret-
bearing evidence.
