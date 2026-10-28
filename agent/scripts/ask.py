"""Send one message to the local PR Wrangler server and print what happened.

    uv run python scripts/ask.py "List the open PRs"

Prints every tool call in order (subagent calls are indented), then the final answer.
"""

import asyncio
import json
import sys
from pathlib import Path

from langgraph_sdk import get_client

ENV = Path(__file__).resolve().parent.parent / ".env"


def langsmith_key():
    for line in ENV.read_text().splitlines():
        if line.startswith("LANGSMITH_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("LANGSMITH_API_KEY missing from .env")


def short(value, limit=160):
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "…"


async def main(message: str):
    client = get_client(url="http://127.0.0.1:2024", api_key=langsmith_key())
    thread = await client.threads.create()
    async for chunk in client.runs.stream(
        thread["thread_id"],
        "pr-wrangler",
        input={"messages": [{"role": "user", "content": message}]},
        stream_mode="updates",
        stream_subgraphs=True,
    ):
        if chunk.event == "error":
            print("ERROR:", chunk.data)
            return
        if not chunk.event.startswith("updates") or not isinstance(chunk.data, dict):
            continue
        indent = "    " if "|" in chunk.event else ""
        for update in chunk.data.values():
            if not isinstance(update, dict):
                continue
            for msg in update.get("messages") or []:
                if not isinstance(msg, dict):
                    continue
                for call in msg.get("tool_calls") or []:
                    print(f"{indent}-> {call['name']} {short(call['args'])}")
                if msg.get("type") == "tool":
                    print(f"{indent}   <- {msg.get('name')}: {short(msg.get('content'), 120)}")

    state = await client.threads.get_state(thread["thread_id"])
    answer = state["values"]["messages"][-1]["content"]
    print("\n--- answer ---\n" + (answer if isinstance(answer, str) else json.dumps(answer, indent=2)))


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "List the open PRs: number and title only."))
