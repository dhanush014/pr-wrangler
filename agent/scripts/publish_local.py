"""Publish saved results (runs/) to GitHub without running the agent.

    uv run python scripts/publish_local.py

Uses the same code as the agent's publish_to_github tool. Needs GITHUB_TOKEN in .env.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.publish import publish  # noqa: E402

for line in (ROOT / ".env").read_text().splitlines():
    if line.startswith("GITHUB_TOKEN="):
        os.environ["GITHUB_TOKEN"] = line.split("=", 1)[1].strip()

files = {f"/briefs/{p.name}": {"content": p.read_text()} for p in (ROOT.parent / "runs" / "briefs").glob("*.json")}
for name in ("deps.json", "queue.json"):
    if (ROOT.parent / "runs" / name).exists():
        files[f"/{name}"] = {"content": (ROOT.parent / "runs" / name).read_text()}

print(asyncio.run(publish(files)))
