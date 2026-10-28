"""Create the 15 demo PRs on the tiny-todo repo.

    python3 seed.py --local   # build the 15 branches locally only (no push), to check the edits apply
    python3 seed.py           # build, push, and open the PRs on GitHub

Safe to re-run: a PR that is already open for a branch is left alone.
"""

import json
import os
import subprocess
import sys

from prs import PRS, REPO

TEAM_EMAIL = "{}@tiny-todo.example"


def run(*cmd, env=None, capture=False):
    result = subprocess.run(cmd, cwd=REPO, env=env, text=True,
                            capture_output=capture, check=True)
    return result.stdout.strip() if capture else None


def open_pr_branches():
    out = run("gh", "pr", "list", "--state", "open", "--limit", "100",
              "--json", "headRefName,number", capture=True)
    return {p["headRefName"]: p["number"] for p in json.loads(out)}


def main():
    local_only = "--local" in sys.argv
    if run("git", "status", "--porcelain", capture=True):
        sys.exit("todo-app has uncommitted changes; commit or stash them first.")

    existing = {} if local_only else open_pr_branches()

    for pr in PRS:
        branch, base = pr["branch"], pr.get("base", "main")
        if branch in existing:
            print(f"#{existing[branch]:<3} {branch}: already open, skipping")
            continue

        run("git", "checkout", "-q", base)
        run("git", "checkout", "-q", "-B", branch)
        pr["apply"]()

        name = pr["author"]
        env = {**os.environ,
               "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": TEAM_EMAIL.format(name.lower())}
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", pr["title"], env=env)

        if local_only:
            print(f"     {branch}: built locally (base {base})")
            continue

        run("git", "push", "-q", "-u", "-f", "origin", branch)
        url = run("gh", "pr", "create", "--base", base, "--head", branch,
                  "--title", pr["title"], "--body", pr["body"], capture=True)
        number = int(url.rstrip("/").split("/")[-1])
        note = "" if number == pr["n"] else f"  (expected #{pr['n']}; answers in expected.json use the planned numbers)"
        print(f"#{number:<3} {branch}{note}")

    run("git", "checkout", "-q", "main")


if __name__ == "__main__":
    main()
