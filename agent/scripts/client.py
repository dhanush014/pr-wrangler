"""Tiny helper for talking to the local PR Wrangler server (uv run mda dev --no-reload --port 2024)."""

import json
from pathlib import Path

from langgraph_sdk import get_client

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:2024"


class RunFailed(RuntimeError):
    """The run errored. `values` is the agent state at the failure, so partial results survive."""

    def __init__(self, error, values):
        super().__init__(f"run failed: {error}")
        self.values = values


def langsmith_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("LANGSMITH_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("LANGSMITH_API_KEY missing from .env")


async def run(message: str, verbose: bool = True):
    """Run one message on a fresh thread. Returns the thread's final state values."""
    client = get_client(url=URL, api_key=langsmith_key())
    thread = await client.threads.create()
    async for chunk in client.runs.stream(
        thread["thread_id"],
        "pr-wrangler",
        input={"messages": [{"role": "user", "content": message}]},
        stream_mode="updates",
        stream_subgraphs=True,
    ):
        if chunk.event == "error":
            state = await client.threads.get_state(thread["thread_id"])
            raise RunFailed(chunk.data, state["values"])
        if not verbose or not chunk.event.startswith("updates") or not isinstance(chunk.data, dict):
            continue
        indent = "    " if "|" in chunk.event else ""
        for update in chunk.data.values():
            for msg in (update or {}).get("messages") or [] if isinstance(update, dict) else []:
                if isinstance(msg, dict):
                    for call in msg.get("tool_calls") or []:
                        args = json.dumps(call["args"])
                        print(f"{indent}-> {call['name']} {args[:140]}")
    state = await client.threads.get_state(thread["thread_id"])
    return state["values"]


def task_results(messages, subagent: str | None = None):
    """Tool results returned by subagents (the `task` tool), optionally for one subagent."""
    calls = {}
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            if call["name"] == "task":
                calls[call["id"]] = call["args"].get("subagent_type")
    results = []
    for msg in messages:
        if msg.get("type") == "tool" and msg.get("name") == "task":
            if subagent is None or calls.get(msg.get("tool_call_id")) == subagent:
                results.append(msg["content"])
    return results


def stored_json(values, path: str):
    """A JSON file the agent saved in its state (see middleware/stash_results.py)."""
    entry = (values.get("files") or {}).get(path)
    if entry is None:
        return None
    content = entry["content"]
    return json.loads(content if isinstance(content, str) else "\n".join(content))
