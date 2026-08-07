#!/usr/bin/env python3
"""Safely commit an image promotion to main from a disposable CI checkout."""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path


TARGETS = {
    "flask": (Path("flask-app/values-production.yaml"), "helm"),
    "lead-magnets": (Path("lead-magnets-chart/values.yaml"), "helm"),
    "private-platform": (Path("private-platform-manifests/private-platform.yaml"), "private"),
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def update(target: str, image: str) -> Path:
    path, kind = TARGETS[target]
    text = path.read_text()
    if kind == "helm":
        updated, count = re.subn(
            r"(?m)^(image:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+tag:)\s*.*$",
            rf"\g<1> {image}",
            text,
            count=1,
        )
        expected = 1
    else:
        updated, count = re.subn(
            r"stevedevopslab6280\.azurecr\.io/platform-portal-private:[a-f0-9]{7,64}",
            image,
            text,
        )
        expected = 2
    if count != expected:
        raise RuntimeError(f"Expected {expected} image reference(s) in {path}, found {count}")
    path.write_text(updated)
    return path


def promote(target: str, image: str, message: str, attempts: int) -> str:
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    for attempt in range(1, attempts + 1):
        run("git", "fetch", "--no-tags", "origin", "main")
        # CI owns this disposable checkout. Rebuild from the latest remote tree so a
        # stale generated commit is never merged over intervening work.
        run("git", "reset", "--hard", "origin/main")
        path = update(target, image)
        run("git", "add", "--", str(path))
        if run("git", "diff", "--cached", "--quiet", "--", str(path), check=False).returncode == 0:
            print(f"{path} already references {image}; promotion is a no-op.")
            return "noop"
        run("git", "commit", "-m", message, "--", str(path))
        pushed = run("git", "push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            print(f"Promoted {image} in {path}.")
            return "promoted"
        if attempt == attempts:
            raise RuntimeError(
                f"Promotion push failed after {attempts} attempts:\n{pushed.stderr.strip()}"
            )
        print(f"main advanced during promotion; replaying on origin/main ({attempt}/{attempts}).")
        time.sleep(attempt * 2)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("image")
    parser.add_argument("message")
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 10:
        parser.error("--attempts must be between 1 and 10")
    promote(args.target, args.image, args.message, args.attempts)


if __name__ == "__main__":
    main()
