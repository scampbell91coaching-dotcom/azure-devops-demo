#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck disable=SC1091 # Runtime-relative repository library.
source "$SCRIPT_DIR/keepass-common.sh"

if [[ $# -ne 1 ]]; then printf 'Usage: %s DATABASE.kdbx\n' "${0##*/}" >&2; exit 2; fi
DATABASE=$1
keepass_require_database "$DATABASE"
keepass_read_password
trap keepass_forget_password EXIT INT TERM

if ! keepass_cli ls -q "$DATABASE" >/dev/null; then
  printf 'ERROR: database unlock failed.\n' >&2
  exit 1
fi

failures=0
for group in "${KEEPASS_GROUPS[@]}"; do
  if keepass_cli ls -q "$DATABASE" "$group" >/dev/null 2>&1; then
    printf 'PASS group     %s\n' "$group"
  else
    printf 'FAIL group     %s\n' "$group"
    failures=$((failures + 1))
  fi
done
for entry in "${KEEPASS_METADATA_ENTRIES[@]}"; do
  # show output is discarded so usernames, notes, and passwords cannot be exposed.
  if keepass_cli show -q "$DATABASE" "$entry" >/dev/null 2>&1; then
    printf 'PASS metadata  %s\n' "$entry"
  else
    printf 'FAIL metadata  %s\n' "$entry"
    failures=$((failures + 1))
  fi
done

if (( failures > 0 )); then
  printf 'Validation failed: %d required item(s) missing.\n' "$failures" >&2
  exit 1
fi
printf 'Validation passed: required groups and metadata entries are present.\n'
