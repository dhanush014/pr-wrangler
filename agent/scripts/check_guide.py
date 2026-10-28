"""Phase 4 check: run the review guide on PRs and score the briefs against the planted answers.

    uv run python scripts/check_guide.py          # PRs 1, 2, 3
    uv run python scripts/check_guide.py 2        # just PR 2

Briefs are saved to ../runs/briefs/<pr>.json (outside the agent, so they never deploy).
"""

import asyncio
import json
import sys
import time

from client import ROOT, run, stored_json

OUT = ROOT.parent / "runs" / "briefs"


def has(text, *words):
    text = text.lower()
    return any(w in text for w in words)


# What a passing brief must contain for each planted PR.
CHECKS = {
    1: [
        ("start_here is in app.js", lambda b: b["start_here"]["file"].endswith("app.js")),
        ("CSS marked as skimmable", lambda b: any("css" in s.lower() for s in b["skim"])),
    ],
    2: [
        ("finds the removed delete confirmation",
         lambda b: any(has(f["code"] + f["issue"], "confirm") for f in b["findings"])),
        ("start_here is in app.js", lambda b: b["start_here"]["file"].endswith("app.js")),
    ],
    3: [
        ("finds the inverted filter as a bug",
         lambda b: any(f["severity"] == "bug" and has(f["code"] + f["issue"], "filter", "t.done")
                       for f in b["findings"])),
        ("start_here points at the filter line", lambda b: "filter" in b["start_here"]["code"]),
        ("risk is not low", lambda b: b["risk"] != "low"),
    ],
}


async def check(pr: int) -> bool:
    started = time.time()
    values = await run(
        f"Use the review-guide subagent on PR #{pr}. Then reply with just the word done.",
        verbose=True,
    )
    brief = stored_json(values, f"/briefs/{pr}.json")
    if brief is None:
        print(f"PR #{pr}: FAIL, no brief saved (last message: {values['messages'][-1]['content'][:200]})")
        return False
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{pr}.json").write_text(json.dumps(brief, indent=2))

    print(f"\nPR #{pr} ({time.time() - started:.0f}s) {brief['kind']}, risk {brief['risk']}: {brief['summary']}")
    print(f"  start here: {brief['start_here']['file']}: {brief['start_here']['code'].strip()}")
    for f in brief["findings"]:
        print(f"  [{f['severity']}] {f['file']}: {f['issue']}")
    ok = True
    for label, test in CHECKS.get(pr, []):
        passed = bool(test(brief))
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return ok


async def main(prs):
    results = {pr: await check(pr) for pr in prs}
    print("\n" + "  ".join(f"#{pr}: {'pass' if ok else 'FAIL'}" for pr, ok in results.items()))
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    asyncio.run(main([int(a) for a in sys.argv[1:]] or [1, 2, 3]))
