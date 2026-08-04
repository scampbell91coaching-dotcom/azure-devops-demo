#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck disable=SC1091 # Runtime-relative repository library.
source "$SCRIPT_DIR/keepass-common.sh"

usage() { printf 'Usage: %s DATABASE.kdbx\n' "${0##*/}"; }

if [[ $# -ne 1 ]]; then usage >&2; exit 2; fi
DATABASE=$1
keepass_require_database "$DATABASE"
keepass_read_password
trap keepass_forget_password EXIT INT TERM

if ! keepass_cli ls -q "$DATABASE" >/dev/null; then
  printf 'ERROR: database unlock failed.\n' >&2
  exit 1
fi

for group in "${KEEPASS_GROUPS[@]}"; do
  if keepass_cli mkdir -q "$DATABASE" "$group" >/dev/null 2>&1; then
    printf 'CREATED  %s\n' "$group"
  else
    # Older keepassxc-cli returns failure when an idempotent mkdir already exists.
    if keepass_cli ls -q "$DATABASE" "$group" >/dev/null 2>&1; then
      printf 'EXISTS   %s\n' "$group"
    else
      printf 'ERROR: could not create or verify group: %s\n' "$group" >&2
      exit 1
    fi
  fi
done

ENTRY=${KEEPASS_METADATA_ENTRIES[0]}
if keepass_cli show -q "$DATABASE" "$ENTRY" >/dev/null 2>&1; then
  printf 'EXISTS   %s\n' "$ENTRY"
else
  CREATED_DATE=$(date -I)
  NOTES=$(printf '%s\n' \
    "Database location: $DATABASE" \
    'Backup location: [record the offline location]' \
    "Date created: $CREATED_DATE" \
    'Emergency recovery procedure: [document and test]' \
    'Last backup test: [YYYY-MM-DD]' '' \
    'Purpose: KeePass database recovery information' \
    "Created: $CREATED_DATE" "Last verified: $CREATED_DATE" \
    'Used by: Traditional Strength' 'Stored elsewhere: No' \
    'Rotation required: No' 'Owner: [named accountable owner]')
  if keepass_cli add -q --username metadata --notes "$NOTES" "$DATABASE" "$ENTRY" >/dev/null; then
    printf 'CREATED  %s\n' "$ENTRY"
  else
    printf 'ERROR: failed to create metadata entry: %s\n' "$ENTRY" >&2
    exit 1
  fi
fi

printf 'KeePass bootstrap completed. No secret values were imported.\n'
