"""Facts the queue planner needs, computed in code.

GitHub only checks each PR against main, so it marks every PR "mergeable" even when two
PRs rewrite the same lines. This tool reads every open PR's diff and reports which PRs
edit the same lines of the same file, which PRs are stacked on another PR's branch, and a
one-line digest of each review brief and the dependency report already saved in /briefs
and /deps.json. The planner model does the judging.
"""

import base64
import json
import os
import re
from itertools import combinations

import httpx
from langchain.tools import ToolRuntime, tool

REPO = "dhanush014/tiny-todo"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def _changed_lines(patch: str):
    """Base-file line numbers this diff deletes, and positions where it inserts."""
    deleted, inserted = set(), set()
    old = 0
    for line in (patch or "").splitlines():
        m = HUNK.match(line)
        if m:
            old = int(m.group(1))
            continue
        if line.startswith("-"):
            deleted.add(old)
            old += 1
        elif line.startswith("+"):
            inserted.add(old)  # inserted before base line `old`
        elif not line.startswith("\\"):
            old += 1
    return deleted, inserted


def _overlap(a, b, eof: int) -> str | None:
    """How two PRs' edits to the same file collide, or None if they don't."""
    del_a, ins_a = a
    del_b, ins_b = b
    # An insertion lands in (or right next to) a block of 2+ lines the other PR replaces.
    # One-line neighbours, like two PRs each adding an import, are only a small conflict.
    def inside(pos, deleted):
        return any({n, n + 1} <= deleted for n in (pos - 2, pos - 1, pos))
    if del_a & del_b or any(inside(p, del_b) for p in ins_a) or any(inside(p, del_a) for p in ins_b):
        return "same-lines"
    spots = {p for p in ins_a & ins_b if p < eof}
    if spots:
        return "same-spot"
    if any(p >= eof for p in ins_a) and any(p >= eof for p in ins_b):
        return "append"
    return None


def _digest(files: dict) -> tuple[dict, dict]:

    def load(path):
        entry = files.get(path)
        if not entry:
            return None
        content = entry["content"]
        return json.loads(content if isinstance(content, str) else "\n".join(content))

    briefs = {}
    for path in files:
        if path.startswith("/briefs/"):
            b = load(path)
            bugs = [f for f in b.get("findings", []) if f["severity"] == "bug"]
            briefs[b["pr"]] = {
                "kind": b["kind"],
                "risk": b["risk"],
                "summary": b["summary"][:140],
                "bugs": [f["issue"][:120] for f in bugs],
                "other_findings": len(b.get("findings", [])) - len(bugs),
            }
    deps = {}
    report = load("/deps.json") or {}
    for v in report.get("prs", []):
        if v.get("flags"):
            deps[v["pr"]] = {"flags": v["flags"], "packages": v.get("packages", []), "why": v["explanation"][:140]}
    return briefs, deps


def _lane(pr: dict, in_collision: bool) -> str:
    """The lane rules are mechanical, so code decides them; the planner orders and explains."""
    brief, flags = pr.get("brief") or {}, (pr.get("dependency_flags") or {}).get("flags", [])
    if "stacked_on" in pr:
        return "blocked"
    if brief.get("bugs") or {"vulnerable", "duplicate"} & set(flags):
        return "fix-first"
    if pr["size"] <= 10 and brief.get("risk") == "low" and not brief.get("other_findings") \
            and not flags and not in_collision:
        return "quick-win"
    return "review"


async def compute_queue_facts(files: dict) -> str:
    """The facts as compact JSON. `files` is the agent's state files (briefs, deps)."""
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        timeout=20,
    ) as gh:
        prs = (await gh.get(f"/repos/{REPO}/pulls", params={"state": "open", "per_page": 100})).json()
        edits, info, main_lengths = {}, {}, {}
        for pr in sorted(prs, key=lambda p: p["number"]):
            n = pr["number"]
            pr_files = (await gh.get(f"/repos/{REPO}/pulls/{n}/files")).json()
            info[n] = {
                "title": pr["title"],
                "size": sum(f["additions"] + f["deletions"] for f in pr_files),
                "files": [f["filename"] for f in pr_files],
            }
            if pr["base"]["ref"] != "main":
                stacked_on = next((p["number"] for p in prs if p["head"]["ref"] == pr["base"]["ref"]), None)
                info[n]["stacked_on"] = stacked_on
                continue  # its diff is against another branch, so line numbers don't line up with main
            edits[n] = {f["filename"]: _changed_lines(f.get("patch", "")) for f in pr_files}
        for path in {p for e in edits.values() for p in e}:
            r = await gh.get(f"/repos/{REPO}/contents/{path}", params={"ref": "main"})
            text = base64.b64decode(r.json()["content"]).decode() if r.status_code == 200 else ""
            main_lengths[path] = len(text.splitlines()) + 1

    # same-lines: both PRs rewrite the same lines, a human has to pick (real collision).
    # same-spot: both insert at the same place, a small mechanical merge conflict.
    # append: both add to the end of the file, trivial; summarised per file.
    same_lines, same_spot, appends = [], [], {}
    for a, b in combinations(sorted(edits), 2):
        for path in sorted(set(edits[a]) & set(edits[b])):
            if path == "package.json":
                continue  # the dependency gate already covers these
            how = _overlap(edits[a][path], edits[b][path], main_lengths.get(path, 10**9))
            if how == "same-lines":
                same_lines.append({"prs": [a, b], "file": path})
            elif how == "same-spot":
                same_spot.append({"prs": [a, b], "file": path})
            elif how == "append":
                appends.setdefault(path, set()).update([a, b])

    briefs, deps = _digest(files)
    colliding = {n for c in same_lines for n in c["prs"]}
    for n in info:
        if n in briefs:
            info[n]["brief"] = briefs[n]
        if n in deps:
            info[n]["dependency_flags"] = deps[n]
        info[n]["lane"] = _lane(info[n], n in colliding)
    # Candidates for "review together": PRs inserting at the same spot in the markup (same part
    # of the UI) or adding the same package. The planner keeps the ones that are one feature.
    only_adds = lambda n: not edits[n]["index.html"][0]  # no deleted lines in the markup
    candidates = [
        {"prs": c["prs"], "signal": "both add new markup at the same spot in the page",
         "same_ui_area": only_adds(c["prs"][0]) and only_adds(c["prs"][1])}
        for c in same_spot if c["file"] == "index.html"
    ]
    by_package = {}
    for n, d in deps.items():
        for pkg in d.get("packages", []):
            by_package.setdefault(pkg.rsplit("@", 1)[0] if not pkg.startswith("@") else pkg, []).append(n)
    candidates += [{"prs": sorted(ns), "signal": f"both add {pkg}", "same_ui_area": True}
                   for pkg, ns in by_package.items() if len(ns) > 1]

    return json.dumps({
        "prs": info,
        "review_together_candidates": candidates,
        "collisions_same_lines": same_lines,
        "small_conflicts_same_spot": same_spot,
        "all_append_to_end_of": {path: sorted(prs) for path, prs in appends.items()},
    }, separators=(",", ":"))


@tool
async def queue_facts(runtime: ToolRuntime) -> str:
    """Facts for planning the review queue: size, base branch, and files of every open PR;
    pairs of PRs that edit the same lines; and a one-line digest of each saved review brief
    and dependency flag. Takes no arguments."""
    return await compute_queue_facts((runtime.state or {}).get("files") or {})


async def open_pr_numbers() -> list[int]:
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        timeout=20,
    ) as gh:
        prs = (await gh.get(f"/repos/{REPO}/pulls", params={"state": "open", "per_page": 100})).json()
    return sorted(p["number"] for p in prs)


LANE_ORDER = ["quick-win", "review", "fix-first", "blocked"]


def _short(text: str, limit: int = 90) -> str:
    text = text.split(". ")[0].rstrip(".")
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _fix_first_reason(pr: dict) -> str | None:
    """Name the actual problem for PRs going back to their author."""
    if pr["lane"] != "fix-first":
        return None
    bugs = (pr.get("brief") or {}).get("bugs") or []
    if bugs:
        return "Bug: " + _short(bugs[0])
    dep = pr.get("dependency_flags") or {}
    return f"{' + '.join(dep.get('flags', []))} dependency: {', '.join(dep.get('packages', []))}"


async def finalize_queue(queue: dict, files: dict) -> dict:
    """Make the planner's queue factually right: code-decided lanes, every open PR exactly once
    in lane order (keeping the model's order inside a lane), blocked PRs, and every collision."""
    facts = json.loads(await compute_queue_facts(files))
    prs = {int(n): info for n, info in facts["prs"].items()}

    reasons, seen, ranked = {}, set(), []
    for item in queue.get("order", []):
        n = item.get("pr")
        if n in prs and n not in seen:
            seen.add(n)
            ranked.append(n)
            reasons[n] = item.get("reason", "")
    ranked += sorted((n for n in prs if n not in seen), key=lambda n: prs[n]["size"])
    order = [
        {"pr": n, "lane": prs[n]["lane"], "reason": _fix_first_reason(prs[n]) or reasons.get(n) or prs[n]["title"]}
        for lane in LANE_ORDER for n in ranked if prs[n]["lane"] == lane
    ]

    advice = {frozenset(c["prs"]): c.get("advice", "") for c in queue.get("collisions", [])}
    collisions = []
    for c in facts["collisions_same_lines"]:
        a, b = c["prs"]
        held = [n for n in (a, b) if prs[n]["lane"] in ("fix-first", "blocked")]
        if len(held) == 1:
            winner, loser = (b, a) if held[0] == a else (a, b)
            text = f"Merge #{winner} first; #{loser} goes back to its author anyway and rebases onto it."
        else:
            text = advice.get(frozenset(c["prs"])) or "Both rewrite the same lines; merge one, then rebase the other."
        collisions.append({"prs": c["prs"], "file": c["file"], "advice": text})
    blocked = [
        {"pr": n, "waits_for": info["stacked_on"], "why": f"Built on #{info['stacked_on']}'s branch."}
        for n, info in sorted(prs.items()) if "stacked_on" in info
    ]
    # The model's groups, plus every candidate code is sure about (same package, or new markup
    # added at the same spot), so a dropped list never loses an obvious pairing.
    together, seen_groups = [], set()
    model_groups = [(g.get("prs", []), g.get("why", "")) for g in queue.get("review_together", [])]
    code_groups = [(c["prs"], c["signal"]) for c in facts.get("review_together_candidates", []) if c.get("same_ui_area")]
    for members, why in model_groups + code_groups:
        key = frozenset(n for n in members if n in prs)
        if len(key) > 1 and key not in seen_groups:
            seen_groups.add(key)
            together.append({"prs": sorted(key), "why": why})

    counts = {lane: sum(1 for o in order if o["lane"] == lane) for lane in LANE_ORDER}
    headline = queue.get("headline") or (
        f"{len(order)} open: {counts['quick-win']} quick wins, {counts['review']} to review, "
        f"{counts['fix-first']} back to authors, {counts['blocked']} blocked."
    )
    return {"headline": headline, "order": order, "review_together": together,
            "collisions": collisions, "blocked": blocked}
