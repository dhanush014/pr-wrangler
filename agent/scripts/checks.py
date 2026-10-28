"""Every check on a full run's output, as data: one entry per check.

Used by check_all.py (prints PASS/FAIL) and langsmith_evals.py (one dataset example per check).
`results` is {"briefs": {pr: brief}, "deps": deps.json, "queue": queue.json or None}.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable

from check_guide import CHECKS as BRIEF_CHECKS
from client import ROOT

EXPECTED = json.loads((ROOT.parent / "seed" / "expected.json").read_text())


@dataclass
class Check:
    id: str  # stable, used as the LangSmith example id
    agent: str  # which subagent's output it scores
    label: str
    expected: str  # the planted answer, in words
    test: Callable[[dict], Any]  # results -> truthy if it passes
    output: Callable[[dict], Any]  # results -> the part of the output it looked at
    detail: Callable[[dict], str] = lambda r: ""


def _queue(r):
    return r.get("queue") or {}


def _lanes(r):
    return {item["pr"]: item["lane"] for item in _queue(r).get("order", [])}


def _groups(r, key):
    return [set(i["prs"]) for i in _queue(r).get(key, [])]


def _flags(r):
    return {v["pr"]: set(v["flags"]) for v in (r.get("deps") or {}).get("prs", [])}


def _dep_entry(r, pr):
    return next((v for v in (r.get("deps") or {}).get("prs", []) if v["pr"] == pr), None)


def _order_item(r, pr):
    return next((i for i in _queue(r).get("order", []) if i["pr"] == pr), None)


def all_checks() -> list[Check]:
    checks = [Check(
        "brief-all-prs", "review-guide", "a brief for every open PR", "15 briefs, PRs #1 to #15",
        lambda r: len(r["briefs"]) == 15,
        lambda r: sorted(r["briefs"]),
        lambda r: f"got {sorted(r['briefs'])}",
    )]
    for pr, tests in BRIEF_CHECKS.items():
        planted = EXPECTED["review_guide"].get(str(pr), {}).get("finding", "")
        for i, (label, test) in enumerate(tests):
            checks.append(Check(
                f"brief-{pr}-{i}", "review-guide", f"#{pr} {label}", planted,
                lambda r, pr=pr, test=test: pr in r["briefs"] and test(r["briefs"][pr]),
                lambda r, pr=pr: r["briefs"].get(pr),
            ))

    dep = EXPECTED["dependency_gate"]
    for pr, want in ((13, "duplicate"), (14, "vulnerable"), (15, "version-drift"), (11, "version-drift")):
        checks.append(Check(
            f"deps-{pr}-{want}", "dependency-gate", f"deps: #{pr} flagged {want}",
            dep[str(pr)].get("finding", f"#{pr} is flagged {want}"),
            lambda r, pr=pr, want=want: want in _flags(r).get(pr, set()),
            lambda r, pr=pr: _dep_entry(r, pr),
        ))
    checks.append(Check(
        "deps-no-false-alarms", "dependency-gate", "deps: no clean PR flagged",
        f"PRs {dep['clean']} have no flags",
        lambda r: not [pr for pr, f in _flags(r).items() if f and pr in dep["clean"]],
        lambda r: {pr: sorted(f) for pr, f in _flags(r).items() if f},
        lambda r: f"flagged {[pr for pr, f in _flags(r).items() if f and pr in dep['clean']]}",
    ))

    q = EXPECTED["queue_planner"]
    checks.append(Check(
        "queue-every-pr-once", "queue-planner", "queue: every PR exactly once", "PRs #1 to #15, each once",
        lambda r: sorted(_lanes(r)) == list(range(1, 16)) and len(_queue(r).get("order", [])) == 15,
        lambda r: [i["pr"] for i in _queue(r).get("order", [])],
        lambda r: f"order has {[i['pr'] for i in _queue(r).get('order', [])]}",
    ))
    for pr in q["quick_wins"]:
        checks.append(Check(
            f"queue-quick-win-{pr}", "queue-planner", f"queue: #{pr} is a quick win", f"#{pr} in the quick-win lane",
            lambda r, pr=pr: _lanes(r).get(pr) == "quick-win",
            lambda r, pr=pr: _order_item(r, pr),
            lambda r, pr=pr: f"lane {_lanes(r).get(pr)}",
        ))
    for a, b in q["collisions"]:
        checks.append(Check(
            f"queue-collide-{a}-{b}", "queue-planner", f"queue: #{a} and #{b} collide",
            f"#{a} and #{b} edit the same lines",
            lambda r, a=a, b=b: any({a, b} <= g for g in _groups(r, "collisions")),
            lambda r: _queue(r).get("collisions"),
        ))
    for a, b in q["review_together"]:
        checks.append(Check(
            f"queue-together-{a}-{b}", "queue-planner", f"queue: #{a} and #{b} reviewed together",
            f"#{a} and #{b} belong in one review",
            lambda r, a=a, b=b: any({a, b} <= g for g in _groups(r, "review_together")),
            lambda r: _queue(r).get("review_together"),
        ))
    for pr, waits in q["blocked"].items():
        checks.append(Check(
            f"queue-blocked-{pr}", "queue-planner", f"queue: #{pr} blocked by #{waits}",
            f"#{pr} is stacked on #{waits} and waits for it",
            lambda r, pr=int(pr), waits=waits: any(
                x["pr"] == pr and x["waits_for"] == waits for x in _queue(r).get("blocked", [])),
            lambda r: _queue(r).get("blocked"),
        ))
    for pr in (3, 14):
        checks.append(Check(
            f"queue-fix-first-{pr}", "queue-planner", f"queue: #{pr} goes back to its author (fix-first)",
            f"#{pr} has a real problem, so it's in the fix-first lane",
            lambda r, pr=pr: _lanes(r).get(pr) == "fix-first",
            lambda r, pr=pr: _order_item(r, pr),
            lambda r, pr=pr: f"lane {_lanes(r).get(pr)}",
        ))
    return checks


def load_saved(runs) -> dict:
    """The results saved by the last check_all.py run (runs/briefs/*.json, deps.json, queue.json)."""
    briefs = {int(p.stem): json.loads(p.read_text()) for p in (runs / "briefs").glob("*.json")}
    deps = json.loads((runs / "deps.json").read_text()) if (runs / "deps.json").exists() else {}
    queue = json.loads((runs / "queue.json").read_text()) if (runs / "queue.json").exists() else None
    return {"briefs": briefs, "deps": deps, "queue": queue}
