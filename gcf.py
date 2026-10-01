#!/usr/bin/env python3
# Copyright (c) 2026 JaeHwan Jin
# SPDX-License-Identifier: GPL-2.0-only
"""Report open pull requests that have become conflicted or lost their CI.

GitHub sends no notification when a pull request starts conflicting, so poll
for it. Prints one line per pull request whose state changed since the last
run and stays quiet otherwise, which suits a scheduled task.

Needs nothing but a Python 3.9 or newer interpreter and a GitHub token with
read access to the repository.

    python gcf.py --token ghp_xxx --author alice
    python gcf.py --token-file token.txt --author alice --author bob

The token can also come from the GITHUB_TOKEN or GH_TOKEN environment
variable, in which case neither option is needed.

Exits 1 when something changed, 0 when nothing did, so a wrapper can decide
whether to raise a notification.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def state_path() -> Path:
    """Somewhere per-user to remember what was already reported."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "pr-watch" / "state.json"


def get(url: str, token: str, retries: int = 3):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pr-watch",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429) and attempt < retries - 1:
                # Secondary rate limit; the header says how long to wait.
                time.sleep(int(err.headers.get("Retry-After", 30)))
                continue
            raise


def open_pulls(repo: str, author: str, token: str):
    q = urllib.parse.quote(f"repo:{repo} is:pr is:open author:{author}")
    found = get(f"{API}/search/issues?q={q}&per_page=100", token)
    return [item["number"] for item in found.get("items", [])]


def failing_checks(repo: str, sha: str, token: str):
    runs = get(f"{API}/repos/{repo}/commits/{sha}/check-runs?per_page=100", token)
    return sorted({
        run["name"] for run in runs.get("check_runs", [])
        if run.get("conclusion") in ("failure", "timed_out", "action_required")
    })


def inspect(repo: str, number: int, token: str):
    """Mergeability is computed in the background, so it can come back null."""
    for attempt in range(3):
        pull = get(f"{API}/repos/{repo}/pulls/{number}", token)
        if pull.get("mergeable") is not None or attempt == 2:
            break
        time.sleep(3)

    if pull.get("mergeable") is None:
        mergeable = "unknown"
    elif pull["mergeable"]:
        mergeable = "mergeable"
    else:
        mergeable = "conflicting"

    checks = failing_checks(repo, pull["head"]["sha"], token)
    return mergeable, checks, pull["title"]


def read_token(args) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name].strip()
    sys.exit("No token. Pass --token or --token-file, or set GITHUB_TOKEN.")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--token", help="GitHub token")
    p.add_argument("--token-file", help="file holding the token")
    p.add_argument("--author", action="append", required=True,
                   help="GitHub login whose pull requests to watch, repeatable")
    p.add_argument("--repo", default="zephyrproject-rtos/zephyr")
    p.add_argument("--state", type=Path, default=state_path(),
                   help="where to remember what was already reported")
    p.add_argument("--all", action="store_true",
                   help="report every pull request, not only the changed ones")
    args = p.parse_args()

    token = read_token(args)

    try:
        previous = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}

    current, changed = {}, False

    for author in args.author:
        for number in open_pulls(args.repo, author, token):
            mergeable, checks, title = inspect(args.repo, number, token)
            key = str(number)
            current[key] = {"mergeable": mergeable, "checks": checks}

            if not args.all and previous.get(key) == current[key]:
                continue

            if mergeable == "conflicting":
                print(f"#{number} CONFLICTING  {title}  ({author})")
                changed = True
            elif checks:
                print(f"#{number} CI failed [{', '.join(checks)}]  {title}  ({author})")
                changed = True
            elif args.all:
                print(f"#{number} ok  {title}  ({author})")

    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(current, indent=1), encoding="utf-8")

    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
