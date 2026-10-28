"""Remote MCP servers: GitHub (read-only) and, when configured, Slack.

X-MCP-Tools keeps the tool list short: every tool schema costs tokens on every model
call, and Groq's free tier allows 8,000 tokens per minute.
"""

import os

from managed_deepagents import define_mcp

READ_TOOLS = [
    "list_pull_requests",
    "pull_request_read",
    "get_file_contents",
    "issue_read",
]

SERVERS = {
    "github": {
        "transport": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
            "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
            "X-MCP-Tools": ",".join(READ_TOOLS),
            "X-MCP-Readonly": "true",
            # PR text is untrusted input; lockdown filters content from people without push access.
            "X-MCP-Lockdown": "true",
        },
        "include_tools": READ_TOOLS,
    },
}

# Slack's MCP server, only when a Slack user token (xoxp-, from an internal Slack app) is set and
# there is no bot token. With a bot token, posting goes through the bot instead (agent.py).
if os.environ.get("SLACK_USER_TOKEN") and not os.environ.get("SLACK_BOT_TOKEN"):
    SERVERS["slack"] = {
        "transport": "http",
        "url": "https://mcp.slack.com/mcp",
        "headers": {"Authorization": f"Bearer {os.environ['SLACK_USER_TOKEN']}"},
    }

mcp = define_mcp(servers=SERVERS)
