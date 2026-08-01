#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${REPO:-$HOME/azure-devops-demo}"
CONTENT_DIR="$REPO/platform-portal/content/lead_magnets"

[[ $# -ge 3 ]] || {
  echo "Usage: $0 SOURCE_SLUG NEW_SLUG NEW_TITLE"
  echo 'Example: ./tools/clone-lead-magnet.sh hip-pain shoulder-pain "The Lifter'\''s Guide to Training Around Shoulder Pain"'
  exit 1
}

SOURCE="$1"
TARGET="$2"
TITLE="$3"

SOURCE_FILE="$CONTENT_DIR/$SOURCE.json"
TARGET_FILE="$CONTENT_DIR/$TARGET.json"

[[ -f "$SOURCE_FILE" ]] || {
  echo "Missing source: $SOURCE_FILE"
  exit 1
}

[[ ! -e "$TARGET_FILE" ]] || {
  echo "Refusing to overwrite: $TARGET_FILE"
  exit 1
}

python3 - "$SOURCE_FILE" "$TARGET_FILE" "$TARGET" "$TITLE" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
slug = sys.argv[3]
title = sys.argv[4]

data = json.loads(source.read_text())
data["slug"] = slug
data["title"] = title
data["cta_heading"] = f"Get the free {slug.replace('-', ' ')} guide"
data["download_label"] = title

target.write_text(json.dumps(data, indent=2) + "\\n")
print(f"Created {target}")
print("Now edit the new JSON file to replace the copied body copy.")
PY
