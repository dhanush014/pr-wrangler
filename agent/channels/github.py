"""GitHub webhook -> PR Wrangler run.

Point a repo webhook (content type application/json, events: Pull requests + Issue comments)
at  https://<deployment-url>/channels/github/events  with secret GITHUB_WEBHOOK_SECRET.

All events for the repo share one thread, so the review briefs saved by earlier runs stay
in state: when one PR changes, only that PR is re-reviewed before the queue is re-planned.
"""

import hashlib
import hmac
import json
import os
import uuid

from managed_deepagents import HttpChannelParseResult, HttpChannelRequest, channels
from starlette.responses import JSONResponse

REPO = "dhanush014/tiny-todo"
THREAD_NAMESPACE = uuid.UUID("0b6f8f0e-3c1d-4a5e-9f2a-6d7c8b9a0e1f")
PR_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review", "closed"}


def verify(context: HttpChannelRequest) -> bool:
    secret = os.environ["GITHUB_WEBHOOK_SECRET"].encode()
    expected = "sha256=" + hmac.new(secret, context.raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, context.request.headers.get("x-hub-signature-256", ""))


def parse(context: HttpChannelRequest) -> HttpChannelParseResult:
    kind = context.request.headers.get("x-github-event", "")
    event = json.loads(context.raw_body)
    if kind == "ping":
        return {"type": "ignore", "response": JSONResponse({"ok": True})}
    if event.get("repository", {}).get("full_name") != REPO:
        return {"type": "ignore"}

    if kind == "pull_request" and event.get("action") in PR_ACTIONS:
        number, action = event["number"], event["action"]
        if action == "closed":
            content = f"PR #{number} was closed. Re-plan the queue without it and publish."
        else:
            content = (
                f"PR #{number} was {action.replace('_', ' ')}. Review PR #{number} again, re-check "
                "dependencies, re-plan the queue, and publish."
            )
    elif kind == "issue_comment" and event.get("action") == "created" \
            and event["comment"]["body"].strip().lower().startswith("/wrangle"):
        content = "Wrangle the queue."
    else:
        return {"type": "ignore"}

    return {
        "type": "message",
        "message": {
            "user_id": str(event["sender"]["id"]),
            "thread_id": str(uuid.uuid5(THREAD_NAMESPACE, REPO)),
            "content": content,
            "target": REPO,
        },
    }


# No `post`: the agent publishes its own results to GitHub with publish_to_github.
channel = channels.http(provider="github", verify=verify, parse=parse)
