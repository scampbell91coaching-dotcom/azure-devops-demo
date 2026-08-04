#!/usr/bin/env bash
set -Eeuo pipefail

if git ls-files -- '*.kdbx' '*.kdbx.lock' | grep -q .; then
  printf 'ERROR: KeePass database or lock files are tracked by Git:\n' >&2
  git ls-files -- '*.kdbx' '*.kdbx.lock' >&2
  exit 1
fi

printf 'No KeePass database or lock files are tracked.\n'
