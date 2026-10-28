"""Wipe everything the agent wrote, so the demo can be recorded again. The 15 PRs stay open.

    python3 reset.py

Convention the agent must follow so this works:
  - every comment or review comment it writes contains the marker <!-- pr-wrangler -->
  - every label it creates starts with one of LABEL_PREFIXES (queue:, lane:, risk:, deps:, pr-wrangler:)
  - the Review Queue issue has the label "pr-wrangler:queue"
"""

import json
import subprocess

from prs import REPO

MARKER = "<!-- pr-wrangler -->"
LABEL_PREFIXES = ("queue:", "lane:", "deps:", "risk:", "pr-wrangler:")


def gh(*args):
    out = subprocess.run(["gh", *args], cwd=REPO, text=True, capture_output=True, check=True).stdout
    return json.loads(out) if out.strip().startswith(("[", "{")) else out


def repo_name():
    return gh("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]


def main():
    repo = repo_name()

    # Comments on PRs and issues (the guide comment, the queue issue body comments)
    comments = gh("api", "--paginate", f"repos/{repo}/issues/comments?per_page=100")
    for c in comments:
        if MARKER in (c.get("body") or ""):
            gh("api", "-X", "DELETE", f"repos/{repo}/issues/comments/{c['id']}")
            print(f"deleted comment {c['id']}")

    # Inline review comments ("Start here")
    review_comments = gh("api", "--paginate", f"repos/{repo}/pulls/comments?per_page=100")
    for c in review_comments:
        if MARKER in (c.get("body") or ""):
            gh("api", "-X", "DELETE", f"repos/{repo}/pulls/comments/{c['id']}")
            print(f"deleted review comment {c['id']}")

    # Review Queue issue
    for issue in gh("issue", "list", "--label", "pr-wrangler:queue", "--state", "open", "--json", "number"):
        gh("issue", "unpin", str(issue["number"]))
        gh("issue", "close", str(issue["number"]), "--reason", "not planned")
        print(f"closed queue issue #{issue['number']}")

    # Labels (deleting a label removes it from every PR)
    for label in gh("label", "list", "--limit", "200", "--json", "name"):
        if label["name"].startswith(LABEL_PREFIXES):
            gh("label", "delete", label["name"], "--yes")
            print(f"deleted label {label['name']}")

    print("reset done")


if __name__ == "__main__":
    main()
