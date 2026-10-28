"""The Slack messages PR Wrangler sends, written in code from the saved queue.

The orchestrator calls slack_messages, then sends each message through the Slack MCP server
(slack_send_message). Code writes the text so it always matches the queue on GitHub; Slack
MCP does the sending.

- Digest: one message to SLACK_DIGEST_CHANNEL with quick wins, PRs going back to authors,
  collisions, review-together groups, blocked PRs, and a link to the Review Queue issue.
- DMs: one per PR in the fix-first lane, to that PR's author. team.json maps commit author
  names (the seven teammates) to Slack member IDs; "*" is the fallback for anyone unlisted.
"""

import json
import os
import re
from pathlib import Path

import httpx
from langchain.tools import ToolRuntime, tool

from tools.publish import QUEUE_DATA_END, QUEUE_DATA_START

REPO = "dhanush014/tiny-todo"
TEAM = Path(__file__).resolve().parent.parent / "team.json"


def _pr(n: int, title: str = "") -> str:
    link = f"<https://github.com/{REPO}/pull/{n}|#{n}>"
    return f"{link} {title}".strip()


def _code_packages(text: str) -> str:
    """Wrap name@version in backticks so Slack doesn't turn it into an email link."""
    return re.sub(r"(?<![`\w])([\w./-]+@[\^~]?\d[\w.-]*)", r"`\1`", text)


def build_messages(queue: dict, titles: dict, authors: dict, team: dict, queue_issue: int | None) -> dict:
    by_lane = lambda lane: [o for o in queue["order"] if o["lane"] == lane]
    lines = ["🤠 **PR Wrangler · review queue**", f"**{queue['headline']}**", ""]
    if by_lane("quick-win"):
        lines.append("⚡ **Merge first (quick wins):** " + ", ".join(_pr(o["pr"], titles.get(o["pr"], "")) for o in by_lane("quick-win")))
    if by_lane("fix-first"):
        lines.append("🛠️ **Back to their authors:**")
        lines += [f"   • {_pr(o['pr'])} {_code_packages(o['reason'])}" for o in by_lane("fix-first")]
    if queue.get("collisions"):
        lines.append("💥 **Same lines, different PRs:**")
        lines += [f"   • {' & '.join(_pr(n) for n in c['prs'])}: {c['advice']}" for c in queue["collisions"]]
    if queue.get("review_together"):
        lines.append("🤝 **Review together:** " + "; ".join(" + ".join(_pr(n) for n in g["prs"]) for g in queue["review_together"]))
    if queue.get("blocked"):
        lines.append("⛔ **Blocked:** " + "; ".join(f"{_pr(b['pr'])} waits for {_pr(b['waits_for'])}" for b in queue["blocked"]))
    if queue_issue:
        lines += ["", f"Full queue: <https://github.com/{REPO}/issues/{queue_issue}|🤠 Review Queue>"]

    dms = []
    for o in by_lane("fix-first"):
        author = authors.get(o["pr"], "")
        member = team.get(author) or team.get("*")
        if not member:
            continue
        dms.append({
            "to": member,
            "pr": o["pr"],
            "text": (
                f"👋 Hi {author or 'there'}, your PR {_pr(o['pr'], titles.get(o['pr'], ''))} is going back to you "
                f"before review.\n> {_code_packages(o['reason'])}\nFix it and push; PR Wrangler re-checks it on the next run."
            ),
        })
    return {"digest_channel": os.environ.get("SLACK_DIGEST_CHANNEL", ""), "digest": "\n".join(lines), "dms": dms}


async def _github_context() -> tuple[dict, dict, int | None, dict | None]:
    """PR titles, each PR's commit author name, the open Review Queue issue number, and the
    queue published in that issue (hidden JSON written by tools/publish.py)."""
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        timeout=20,
    ) as gh:
        prs = (await gh.get(f"/repos/{REPO}/pulls", params={"state": "open", "per_page": 100})).json()
        titles = {p["number"]: p["title"] for p in prs}
        authors = {}
        for p in prs:
            commits = (await gh.get(f"/repos/{REPO}/pulls/{p['number']}/commits")).json()
            authors[p["number"]] = commits[-1]["commit"]["author"]["name"] if commits else ""
        issues = (await gh.get(f"/repos/{REPO}/issues", params={"labels": "pr-wrangler:queue", "state": "open"})).json()
    if not issues:
        return titles, authors, None, None
    body = issues[0]["body"] or ""
    start = body.find(QUEUE_DATA_START)
    published = None
    if start != -1:
        raw = body[start + len(QUEUE_DATA_START):body.find(QUEUE_DATA_END, start)]
        published = json.loads(raw)
    return titles, authors, issues[0]["number"], published


async def compute_slack_messages(files: dict) -> dict:
    """Uses the queue from this run if there is one, otherwise the last one published to GitHub."""
    titles, authors, issue, published = await _github_context()
    entry = files.get("/queue.json")
    if entry:
        content = entry["content"]
        queue = json.loads(content if isinstance(content, str) else "\n".join(content))
    elif published:
        queue = published
    else:
        return {"error": "No queue yet. Wrangle the queue first."}
    team = json.loads(TEAM.read_text()) if TEAM.exists() else {}
    return build_messages(queue, titles, authors, team, issue)


@tool
async def slack_messages(runtime: ToolRuntime) -> str:
    """The Slack messages to send for the current review queue: one digest for the team channel
    and one DM per PR that goes back to its author. Returns JSON with digest_channel, digest,
    and dms (each with `to`, a Slack member ID, and `text`). Send each one with the Slack MCP
    send-message tool, exactly as written. Takes no arguments."""
    return json.dumps(await compute_slack_messages((runtime.state or {}).get("files") or {}))


async def _bot_call(client: httpx.AsyncClient, method: str, payload: dict) -> dict:
    r = await client.post(f"https://slack.com/api/{method}", json=payload)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {data.get('error')}")
    return data


async def post_as_bot(messages: dict) -> dict:
    """Send the digest and DMs as the PR Wrangler bot (SLACK_BOT_TOKEN), via Slack's Web API.

    Slack MCP only accepts user tokens, so anything sent through it shows up as the person who
    installed the app. Posting as the bot makes the messages come from "PR Wrangler" itself.
    """
    # The Web API uses Slack mrkdwn: *bold*, not **bold**.
    mrkdwn = lambda text: text.replace("**", "*")
    sent = {"digest": None, "dms": []}
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}, timeout=20
    ) as client:
        if messages.get("digest_channel"):
            posted = await _bot_call(client, "chat.postMessage", {
                "channel": messages["digest_channel"], "text": mrkdwn(messages["digest"]), "unfurl_links": False,
            })
            sent["digest"] = posted["ts"]
        for dm in messages.get("dms", []):
            channel = (await _bot_call(client, "conversations.open", {"users": dm["to"]}))["channel"]["id"]
            posted = await _bot_call(client, "chat.postMessage", {
                "channel": channel, "text": mrkdwn(dm["text"]), "unfurl_links": False,
            })
            sent["dms"].append({"pr": dm["pr"], "ts": posted["ts"]})
    return sent


@tool
async def post_slack_digest(runtime: ToolRuntime) -> str:
    """Post the review-queue digest to the team channel and DM every author whose PR goes back
    to them, as the PR Wrangler bot. Uses the queue from this run, or the last one published to
    GitHub. Takes no arguments."""
    messages = await compute_slack_messages((runtime.state or {}).get("files") or {})
    if "error" in messages:
        return messages["error"]
    sent = await post_as_bot(messages)
    return (
        f"Posted the digest to {messages['digest_channel']} and {len(sent['dms'])} DMs "
        f"(PRs {', '.join('#' + str(d['pr']) for d in sent['dms']) or 'none'}) as PR Wrangler."
    )
