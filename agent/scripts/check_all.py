"""End-to-end check: one "wrangle the queue" run, scored against seed/expected.json.

    uv run python scripts/check_all.py

Everything the agent saved goes to runs/: briefs/<pr>.json, deps.json, queue.json.
"""

import asyncio
import json
import sys
import time

from checks import all_checks
from client import ROOT, RunFailed, run, stored_json

RUNS = ROOT.parent / "runs"


def report(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail and not ok else ""))
    return ok


async def main():
    started = time.time()
    failure = None
    try:
        values = await run("Wrangle the queue.", verbose=True)
    except RunFailed as error:
        failure, values = error, error.values
    elapsed = time.time() - started

    files = values.get("files") or {}
    briefs = {int(p.split("/")[-1].split(".")[0]): stored_json(values, p) for p in files if p.startswith("/briefs/")}
    deps = stored_json(values, "/deps.json") or {}
    queue = stored_json(values, "/queue.json")

    RUNS.mkdir(exist_ok=True)
    (RUNS / "briefs").mkdir(exist_ok=True)
    for pr, b in briefs.items():
        (RUNS / "briefs" / f"{pr}.json").write_text(json.dumps(b, indent=2))
    if deps:
        (RUNS / "deps.json").write_text(json.dumps(deps, indent=2))
    if queue:
        (RUNS / "queue.json").write_text(json.dumps(queue, indent=2))

    print(f"\nRun took {elapsed / 60:.1f} min. Final reply: {values['messages'][-1]['content'][:300]}\n")
    if failure:
        print(f"RUN FAILED: {failure}. Partial results saved to {RUNS}.\n")
    if queue is not None:
        print(f"  Headline: {queue['headline']}")
        for item in queue["order"]:
            print(f"    #{item['pr']:<3} {item['lane']:<10} {item['reason']}")
        print()
    results = {"briefs": briefs, "deps": deps, "queue": queue}
    ok = report("queue saved", queue is not None)
    for check in all_checks():
        ok &= report(check.label, bool(check.test(results)), check.detail(results))
    ok &= report("run finished without an error", failure is None)
    print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
