"""Phase 5 check: run the dependency gate and compare its flags with the planted answers.

    uv run python scripts/check_deps.py

The report is saved to runs/deps.json.
"""

import asyncio
import json
import sys
import time

from client import ROOT, run, stored_json

# PR -> flags it must have. Every other PR must come back clean.
REQUIRED = {13: {"duplicate"}, 14: {"vulnerable"}, 15: {"version-drift"}, 11: {"version-drift"}}


async def main():
    started = time.time()
    values = await run("Run the dependency-gate subagent once for the whole queue. Then reply with just the word done.")
    report = stored_json(values, "/deps.json")
    if report is None:
        print("FAIL: no dependency report saved. Last message:", values["messages"][-1]["content"][:300])
        sys.exit(1)
    (ROOT.parent / "runs").mkdir(exist_ok=True)
    (ROOT.parent / "runs" / "deps.json").write_text(json.dumps(report, indent=2))

    print(f"\nDependency report ({time.time() - started:.0f}s)")
    flagged = {}
    for v in report["prs"]:
        flagged[v["pr"]] = set(v["flags"])
        print(f"  #{v['pr']} {v['packages']} flags={v['flags']}\n      {v['explanation']}\n      -> {v['suggestion']}")

    ok = True
    for pr, need in REQUIRED.items():
        missing = need - flagged.get(pr, set())
        print(f"  {'PASS' if not missing else 'FAIL'}  #{pr} flagged {sorted(need)}" + (f" (missing {sorted(missing)})" if missing else ""))
        ok &= not missing
    false_alarms = [pr for pr, flags in flagged.items() if flags and pr not in REQUIRED]
    print(f"  {'PASS' if not false_alarms else 'FAIL'}  no other PR flagged" + (f" (flagged: {false_alarms})" if false_alarms else ""))
    ok &= not false_alarms
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
