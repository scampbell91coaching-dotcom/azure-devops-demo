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
    "private-platform": (
        (
            Path("private-platform-manifests/private-platform.yaml"),
            Path("private-platform-manifests/platform-status-collector.yaml"),
        ),
        "private",
    ),
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def update(target: str, image: str) -> tuple[Path, ...]:
    configured_paths, kind = TARGETS[target]
    paths = (
        configured_paths
        if isinstance(configured_paths, tuple)
        else (configured_paths,)
    )
    total = 0
    for path in paths:
        text = path.read_text()
        if kind == "helm":
            updated, count = re.subn(
                r"(?m)^(image:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+tag:)\s*.*$",
                rf"\g<1> {image}",
                text,
                count=1,
            )
        else:
            updated, count = re.subn(
                r"stevedevopslab6280\.azurecr\.io/platform-portal-private:[a-f0-9]{7,64}",
                image,
                text,
            )
        path.write_text(updated)
        total += count
    expected = 1 if kind == "helm" else 3
    if total != expected:
        raise RuntimeError(f"Expected {expected} image reference(s) in {paths}, found {total}")
    return paths


def promote(target: str, image: str, message: str, attempts: int) -> str:
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    for attempt in range(1, attempts + 1):
        run("git", "fetch", "--no-tags", "origin", "main")
        # CI owns this disposable checkout. Rebuild from the latest remote tree so a
        # stale generated commit is never merged over intervening work.
        run("git", "reset", "--hard", "origin/main")
        paths = update(target, image)
        path_args = tuple(str(path) for path in paths)
        run("git", "add", "--", *path_args)
        if run("git", "diff", "--cached", "--quiet", "--", *path_args, check=False).returncode == 0:
            print(f"{paths} already reference {image}; promotion is a no-op.")
            return "noop"
        run("git", "commit", "-m", message, "--", *path_args)
        pushed = run("git", "push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            print(f"Promoted {image} in {paths}.")
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
