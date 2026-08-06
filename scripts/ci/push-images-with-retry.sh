#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 IMAGE [IMAGE ...]" >&2
  exit 2
fi

for image in "$@"; do
  for attempt in 1 2 3; do
    echo "Pushing ${image} (attempt ${attempt}/3)"
    if docker push "$image"; then
      break
    fi

    if [ "$attempt" -eq 3 ]; then
      echo "ERROR: failed to push ${image} after 3 attempts" >&2
      exit 1
    fi

    delay=$((attempt * 20))
    echo "Push failed; retrying in ${delay}s"
    sleep "$delay"
  done
done
