"""Collect dependency changes across every open PR, in code.

Reading 15 diffs (or GitHub's full advisory write-ups, ~15k tokens for lodash alone)
through the model would not fit Groq's 8,000 tokens/minute. This tool does the
mechanical part with the GitHub REST API and returns a compact summary; the
dependency-gate subagent does the judging.
"""

import base64
import json
import os
import re

import httpx
from langchain.tools import tool

REPO = "dhanush014/tiny-todo"
API = "https://api.github.com"


def _client():
    return httpx.AsyncClient(
        base_url=API,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
        timeout=20,
    )


async def _package_json(client, ref: str) -> dict:
    r = await client.get(f"/repos/{REPO}/contents/package.json", params={"ref": ref})
    r.raise_for_status()
    pkg = json.loads(base64.b64decode(r.json()["content"]))
    return {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}


def _min_version(spec: str) -> str:
    match = re.search(r"\d+(\.\d+){0,2}", spec)
    return match.group(0) if match else spec


async def _advisories(client, name: str, spec: str) -> list[dict]:
    r = await client.get(
        "/advisories",
        params={"ecosystem": "npm", "affects": f"{name}@{_min_version(spec)}", "per_page": 20},
    )
    r.raise_for_status()
    found = []
    for adv in r.json():
        if adv.get("withdrawn_at"):
            continue
        fixed = {v.get("first_patched_version") for v in adv.get("vulnerabilities", [])} - {None}
        found.append({
            "id": adv["ghsa_id"],
            "severity": adv["severity"],
            "summary": adv["summary"][:120],
            "fixed_in": sorted(fixed),
        })
    return found


@tool
async def dependency_changes() -> str:
    """List every dependency that open pull requests add, change, or remove in package.json,
    with known security advisories for each new version and packages that more than one PR touches.
    Also returns the dependencies already on main. Takes no arguments."""
    async with _client() as client:
        on_main = await _package_json(client, "main")
        prs = (await client.get(f"/repos/{REPO}/pulls", params={"state": "open", "per_page": 100})).json()

        changes, seen = [], {}
        for pr in sorted(prs, key=lambda p: p["number"]):
            files = (await client.get(f"/repos/{REPO}/pulls/{pr['number']}/files")).json()
            if not any(f["filename"] == "package.json" for f in files):
                continue
            on_branch = await _package_json(client, pr["head"]["sha"])
            added = {k: v for k, v in on_branch.items() if k not in on_main}
            changed = {k: [on_main[k], v] for k, v in on_branch.items() if k in on_main and on_main[k] != v}
            removed = sorted(k for k in on_main if k not in on_branch)
            advisories = {}
            for name, spec in {**added, **{k: v[1] for k, v in changed.items()}}.items():
                seen.setdefault(name, []).append({"pr": pr["number"], "version": spec})
                found = await _advisories(client, name, spec)
                if found:
                    advisories[f"{name}@{spec}"] = found
            changes.append({
                "pr": pr["number"],
                "title": pr["title"],
                "added": added,
                "changed": changed,
                "removed": removed,
                "advisories": advisories,
            })

    shared = {name: uses for name, uses in seen.items() if len(uses) > 1}
    return json.dumps({
        "dependencies_on_main": on_main,
        "prs_changing_dependencies": changes,
        "packages_in_more_than_one_pr": shared,
        "prs_without_dependency_changes": sorted(
            p["number"] for p in prs if p["number"] not in {c["pr"] for c in changes}
        ),
    }, separators=(",", ":"))
