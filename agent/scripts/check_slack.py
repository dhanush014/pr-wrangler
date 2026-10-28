"""Check the Slack setup before a run: is the token valid, and what tools does Slack MCP offer?

    uv run python scripts/check_slack.py
"""

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

token = os.environ.get("SLACK_USER_TOKEN", "")
if not (token.startswith("xoxp-") or token.startswith("xoxe.xoxp-")):
    sys.exit("SLACK_USER_TOKEN in .env must be a user token (xoxp- or rotating xoxe.xoxp-)")

me = httpx.post("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {token}"}).json()
if not me.get("ok"):
    sys.exit(f"Token rejected by Slack: {me.get('error')}")
print(f"Token OK: user {me['user']} ({me['user_id']}) in workspace {me['team']}")
print(f"Digest channel: {os.environ.get('SLACK_DIGEST_CHANNEL') or 'NOT SET (add SLACK_DIGEST_CHANNEL to .env)'}")

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
           "Content-Type": "application/json"}


def rpc(client, method, params, session=None, id_=1):
    h = dict(headers, **({"Mcp-Session-Id": session} if session else {}))
    r = client.post("https://mcp.slack.com/mcp", headers=h,
                    json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
    text = r.text
    if "data:" in text:  # streamable HTTP may answer as an event stream
        text = next(l[5:] for l in text.splitlines() if l.startswith("data:"))
    return r, json.loads(text) if text.strip() else {}


with httpx.Client(timeout=30) as client:
    r, init = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "pr-wrangler-check", "version": "1"}})
    if "error" in init or r.status_code >= 400:
        sys.exit(f"Slack MCP refused the token: HTTP {r.status_code} {init.get('error') or r.text[:300]}")
    session = r.headers.get("mcp-session-id")
    client.post("https://mcp.slack.com/mcp", headers=dict(headers, **({"Mcp-Session-Id": session} if session else {})),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    _, listed = rpc(client, "tools/list", {}, session, 2)
    names = [t["name"] for t in listed.get("result", {}).get("tools", [])]
    print(f"Slack MCP tools ({len(names)}): {', '.join(names)}")
    send = [n for n in names if n.endswith("send_message")]
    print("Send tool:", send or "NOT FOUND (tell Claude the list above)")
