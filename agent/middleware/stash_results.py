"""Keep subagent results out of the orchestrator's conversation.

Each subagent returns a structured JSON result (a brief, a dependency report, a queue).
Left alone, every result stays in the orchestrator's message history and is re-sent on
every later model call, which blows through Groq's 8,000 tokens/minute after a few PRs.

This middleware saves each result as a file in the agent's state (/briefs/<pr>.json,
/deps.json, /queue.json) and hands the orchestrator a one-line summary instead.
Other subagents and the publish step read the files.
"""

import json
import re

from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage
from langgraph.types import Command

from tools.queue_facts import finalize_queue, open_pr_numbers


def _path_and_summary(subagent: str, data: dict) -> tuple[str, str] | None:
    if subagent == "review-guide":
        bugs = sum(1 for f in data.get("findings", []) if f.get("severity") == "bug")
        return (
            f"/briefs/{data['pr']}.json",
            f"PR #{data['pr']}: {data.get('kind')}, risk {data.get('risk')}, "
            f"{len(data.get('findings', []))} findings ({bugs} bugs). Saved to /briefs/{data['pr']}.json",
        )
    if subagent == "dependency-gate":
        flagged = [str(p["pr"]) for p in data.get("prs", []) if p.get("flags")]
        return "/deps.json", f"Dependency report saved to /deps.json. Flagged PRs: {', '.join(flagged) or 'none'}"
    if subagent == "queue-planner":
        return "/queue.json", f"Review queue saved to /queue.json ({len(data.get('order', []))} PRs ranked)"
    return None


FIX = re.compile(r"[Ss]hould (?:be|use|read)[: ]+`?([^`]+?)`?(?:\.(?:\s|$)|$)")


def _fix_already_in_code(finding: dict) -> bool:
    """A finding whose suggested fix is already the quoted code is a hallucination."""
    match = FIX.search(finding.get("issue", ""))
    if not match:
        return False
    norm = lambda s: re.sub(r"\s+", "", s)
    return len(match.group(1)) > 8 and norm(match.group(1)) in norm(finding.get("code", ""))


@wrap_tool_call(name="StashSubagentResults")
async def stash_results(request, handler):
    result = await handler(request)
    call = request.tool_call
    if call["name"] != "task" or not isinstance(result, Command):
        return result
    update = dict(result.update or {})
    messages = list(update.get("messages") or [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return result
    try:
        data = json.loads(messages[-1].content)
    except (TypeError, json.JSONDecodeError):
        return result  # not a structured result; leave it as is
    subagent = call["args"].get("subagent_type", "")
    if subagent == "review-guide":
        data["findings"] = [f for f in data.get("findings", []) if not _fix_already_in_code(f)]
    if subagent == "queue-planner":
        data = await finalize_queue(data, (request.state or {}).get("files") or {})
    stash = _path_and_summary(subagent, data)
    if stash is None:
        return result
    path, summary = stash
    files = dict(update.get("files") or {})
    files[path] = create_file_data(json.dumps(data, indent=2))
    update["files"] = files
    update["messages"] = [*messages[:-1], ToolMessage(content=summary, tool_call_id=call["id"], name="task")]
    return Command(update=update)


@wrap_tool_call(name="OnePrPerReview")
async def one_pr_per_review(request, handler):
    """Refuse review-guide tasks that bundle several PRs.

    One bundled task makes the review guide pull every diff into a single request, which
    is far over Groq's per-minute token cap. Refusing it makes the orchestrator split them.
    """
    args = request.tool_call["args"]
    if request.tool_call["name"] == "task" and args.get("subagent_type") == "review-guide":
        prs = set(re.findall(r"#(\d+)", args.get("description", "")))
        if len(prs) > 1:
            return ToolMessage(
                content="Refused: send exactly one PR per review-guide task. "
                "Make a separate task call for each PR, e.g. 'Review PR #3.'",
                tool_call_id=request.tool_call["id"],
                name="task",
                status="error",
            )
    return await handler(request)


@wrap_tool_call(name="AllBriefsBeforePlanning")
async def all_briefs_before_planning(request, handler):
    """Refuse to plan the queue while any open PR has no review brief.

    The orchestrator model sometimes stops after a few reviews. This tells it exactly which
    PRs are still missing instead of letting the planner rank a half-reviewed queue.
    """
    args = request.tool_call["args"]
    if request.tool_call["name"] == "task" and args.get("subagent_type") == "queue-planner":
        files = (request.state or {}).get("files") or {}
        reviewed = {int(p.rsplit("/", 1)[1].split(".")[0]) for p in files if p.startswith("/briefs/")}
        missing = [n for n in await open_pr_numbers() if n not in reviewed]
        if missing or "/deps.json" not in files:
            todo = [f"review-guide for PR #{n}" for n in missing]
            if "/deps.json" not in files:
                todo.append("dependency-gate once")
            return ToolMessage(
                content="Refused: not ready to plan. First delegate " + "; ".join(todo)
                + ". Use one task per PR. Then call queue-planner again.",
                tool_call_id=request.tool_call["id"],
                name="task",
                status="error",
            )
    return await handler(request)
