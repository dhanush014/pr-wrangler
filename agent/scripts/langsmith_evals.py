"""The full-run checks as a LangSmith dataset and experiment.

    uv run python scripts/langsmith_evals.py              # score the run saved in runs/
    uv run python scripts/langsmith_evals.py --sync-only  # just upload the dataset

One dataset example per check in checks.py (the planted answers from seed/expected.json), so
the dataset matches check_all.py exactly. The experiment scores the run saved in runs/ by the
last check_all.py (a full live run takes ~11 minutes and most of Groq's daily tokens, so it
isn't repeated per experiment). For a fresh experiment: scripts/e2e.sh check_all.py, then this.

Each experiment row shows the check, the planted answer, and the part of the agent's output it
looked at. Compare experiments in LangSmith -> Datasets & Experiments -> pr-wrangler-checks.
"""

import argparse
import os
import sys
import uuid
from datetime import datetime

from client import ROOT, langsmith_key

os.environ.setdefault("LANGSMITH_API_KEY", langsmith_key())

from langsmith import Client, evaluate  # noqa: E402

from checks import all_checks, load_saved  # noqa: E402

DATASET = "pr-wrangler-checks"
NS = uuid.UUID("0d3c9f6e-2b8a-4e1f-9a57-7c1e4b2d8f30")  # stable example ids from check ids
RUNS = ROOT.parent / "runs"
CHECKS = {c.id: c for c in all_checks()}
MODELS = {"orchestrator": "openai/gpt-oss-120b", "review-guide": "qwen/qwen3.8-27b",
          "dependency-gate": "qwen/qwen3.8-27b", "queue-planner": "openai/gpt-oss-120b"}


def example_id(check_id: str) -> str:
    return str(uuid.uuid5(NS, check_id))


def sync_dataset(client: Client) -> None:
    """Make the dataset match checks.py: adds, updates or removes only what changed."""
    if client.has_dataset(dataset_name=DATASET):
        dataset = client.read_dataset(dataset_name=DATASET)
    else:
        dataset = client.create_dataset(DATASET, description=(
            "PR Wrangler full-run checks on the 15 seeded tiny-todo PRs: one example per planted answer "
            "(review briefs, dependency flags, review queue). Source: seed/expected.json."))
    wanted = {example_id(c.id): {"inputs": {"check": c.label, "agent": c.agent},
                                 "outputs": {"expected": c.expected},
                                 "metadata": {"check_id": c.id, "agent": c.agent}} for c in CHECKS.values()}
    have = {str(e.id): e for e in client.list_examples(dataset_id=dataset.id)}
    new = [k for k in wanted if k not in have]
    if new:
        client.create_examples(dataset_id=dataset.id, examples=[{"id": k, **wanted[k]} for k in new])
    changed = [k for k in wanted if k in have and (have[k].inputs != wanted[k]["inputs"]
                                                   or have[k].outputs != wanted[k]["outputs"])]
    for k in changed:
        client.update_example(k, inputs=wanted[k]["inputs"], outputs=wanted[k]["outputs"],
                              metadata=wanted[k]["metadata"])
    gone = [k for k in have if k not in wanted]
    if gone:
        client.delete_examples(gone)
    print(f"Dataset {DATASET}: {len(wanted)} examples ({len(new)} added, {len(changed)} updated, {len(gone)} removed)")


def make_target(results: dict):
    by_label = {c.label: c for c in CHECKS.values()}

    def pr_wrangler_check(inputs: dict) -> dict:
        check = by_label[inputs["check"]]
        return {"passed": bool(check.test(results)), "detail": check.detail(results),
                "agent_output": check.output(results)}

    return pr_wrangler_check


def passed(outputs: dict) -> dict:
    return {"key": "passed", "score": int(outputs["passed"]),
            "comment": None if outputs["passed"] else outputs["detail"] or "check failed"}


def pass_rate(outputs: list[dict]) -> dict:
    return {"key": "pass_rate", "score": sum(o["passed"] for o in outputs) / len(outputs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sync-only", action="store_true", help="upload the dataset, run nothing")
    args = parser.parse_args()

    client = Client()
    sync_dataset(client)
    if args.sync_only:
        return

    if not (RUNS / "queue.json").exists():
        sys.exit(f"No saved run in {RUNS}. Run scripts/e2e.sh check_all.py first.")
    run_time = datetime.fromtimestamp((RUNS / "queue.json").stat().st_mtime)
    results = load_saved(RUNS)
    metadata = {"run_saved_at": run_time.isoformat(timespec="minutes"), "briefs": len(results["briefs"]),
                **{f"model_{k}": v for k, v in MODELS.items()}}
    experiment = evaluate(make_target(results), data=DATASET, evaluators=[passed], summary_evaluators=[pass_rate],
                          experiment_prefix=f"full-run-{run_time:%m%d-%H%M}", metadata=metadata,
                          max_concurrency=4, client=client)

    rows = list(experiment)
    failed = [r["example"].inputs["check"] for r in rows if not r["run"].outputs["passed"]]
    print(f"\nExperiment {experiment.experiment_name}: {len(rows) - len(failed)}/{len(rows)} checks pass")
    for label in failed:
        print(f"  FAIL  {label}")
    print(f"Compare experiments: LangSmith -> Datasets & Experiments -> {DATASET}")


if __name__ == "__main__":
    main()
