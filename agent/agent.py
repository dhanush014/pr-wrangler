"""PR Wrangler: the orchestrator plus its subagents."""

import os

from langchain_groq import ChatGroq
from managed_deepagents import define_deep_agent

from middleware.retries import groq_tool_retry
from middleware.stash_results import all_briefs_before_planning, one_pr_per_review, stash_results
from middleware.tool_scope import only_tools
from subagents.dependency_gate import dependency_gate
from subagents.queue_planner import queue_planner
from subagents.review_guide import review_guide
from tools.dependencies import dependency_changes
from tools.publish import publish_to_github
from tools.slack_messages import post_slack_digest, slack_messages

# Groq's free tier limits tokens PER MODEL (8,000/minute, ~200,000/day), so the
# orchestrator and the subagents run on different models to draw from separate allowances.
# Retries ride out per-minute 429s instead of failing the run.
# The orchestrator needs the bigger model: gpt-oss-20b bundled several PRs into one task
# and over-thought the workflow. Its calls are small (~2k tokens), so it shares the 120b
# allowance with the planner's single call.
orchestrator_model = ChatGroq(
    model="openai/gpt-oss-120b", temperature=0, max_retries=8, reasoning_effort="low", max_tokens=4096
)
# qwen on the free tier allows only 1,000 output tokens/minute: no thinking tokens, capped output.
review_model = ChatGroq(
    model="qwen/qwen3.8-27b", temperature=0, max_retries=8, reasoning_effort="none", max_tokens=900
)
dependency_model = review_model
planner_model = ChatGroq(model="openai/gpt-oss-120b", temperature=0, max_retries=8, reasoning_effort="medium")

# Slack is optional. With SLACK_BOT_TOKEN the orchestrator posts the digest and DMs as the
# PR Wrangler bot (post_slack_digest). With only SLACK_USER_TOKEN it sends them through the
# Slack MCP server instead (tools/mcp.py), which shows them as the person who installed the app.
SLACK_BOT = bool(os.environ.get("SLACK_BOT_TOKEN"))
SLACK_MCP = bool(os.environ.get("SLACK_USER_TOKEN")) and not SLACK_BOT
slack_tool_objects = [post_slack_digest] if SLACK_BOT else [slack_messages] if SLACK_MCP else []
slack_tools = ["post_slack_digest"] if SLACK_BOT else ["slack_messages", "slack_*send_message"] if SLACK_MCP else []

agent = define_deep_agent(
    name="pr-wrangler",
    model=orchestrator_model,
    # Subagents inherit these (plus the GitHub MCP tools); each one's middleware picks its own.
    tools=[dependency_changes, publish_to_github, *slack_tool_objects],
    subagents=[
        {**review_guide, "model": review_model},
        {**dependency_gate, "model": dependency_model},
        {**queue_planner, "model": planner_model},
    ],
    middleware=[
        only_tools("task", "github_list_pull_requests", "publish_to_github", "ls", "read_file", *slack_tools),
        one_pr_per_review,
        all_briefs_before_planning,
        stash_results,
        groq_tool_retry(),
    ],
)
