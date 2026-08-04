#!/usr/bin/env bash
set -Eeuo pipefail

usage() { printf 'Usage: %s SOURCE.kdbx DESTINATION.kdbx\n' "${0##*/}"; }
if [[ $# -ne 2 ]]; then usage >&2; exit 2; fi
SOURCE=$1
DESTINATION=$2

[[ -f "$SOURCE" ]] || { printf 'ERROR: source database not found.\n' >&2; exit 1; }

if command -v sha256sum >/dev/null 2>&1; then
  CHECKSUM=(sha256sum --)
elif command -v shasum >/dev/null 2>&1; then
  CHECKSUM=(shasum -a 256 --)
else
  printf 'ERROR: sha256sum or shasum is required for verification.\n' >&2
  exit 1
fi

REPO_ROOT=$(git -C "$(dirname -- "$0")" rev-parse --show-toplevel 2>/dev/null) || {
  printf 'ERROR: cannot determine repository root.\n' >&2; exit 1;
}
DEST_PARENT=$(dirname -- "$DESTINATION")
[[ -d "$DEST_PARENT" ]] || { printf 'ERROR: destination directory does not exist.\n' >&2; exit 1; }
REPO_REAL=$(realpath -- "$REPO_ROOT")
DEST_REAL=$(realpath -- "$DEST_PARENT")/$(basename -- "$DESTINATION")
case "$DEST_REAL" in
  "$REPO_REAL"|"$REPO_REAL"/*) printf 'ERROR: repository destinations are forbidden.\n' >&2; exit 1 ;;
esac

umask 077
TEMP_COPY=''
cleanup() {
  if [[ -n "$TEMP_COPY" ]]; then
    rm -f -- "$TEMP_COPY"
  fi
}
trap cleanup EXIT INT TERM

TEMP_COPY=$(mktemp --tmpdir="$DEST_PARENT" ".${DESTINATION##*/}.tmp.XXXXXXXXXX") || {
  printf 'ERROR: could not create private temporary backup.\n' >&2
  exit 1
}
chmod 600 -- "$TEMP_COPY"
cp -- "$SOURCE" "$TEMP_COPY"

SOURCE_CHECKSUM=$("${CHECKSUM[@]}" "$SOURCE" | awk '{print $1}')
DESTINATION_CHECKSUM=$("${CHECKSUM[@]}" "$TEMP_COPY" | awk '{print $1}')
if [[ "$SOURCE_CHECKSUM" != "$DESTINATION_CHECKSUM" ]]; then
  printf 'ERROR: backup checksum verification failed; destination was not changed.\n' >&2
  exit 1
fi
mv -f -- "$TEMP_COPY" "$DESTINATION"
TEMP_COPY=''
printf 'Backup created and checksum verified: %s\n' "$DESTINATION"
