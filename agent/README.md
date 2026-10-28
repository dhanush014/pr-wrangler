# PR Wrangler 🤠

**AI GitHub PR manager.** Seven developers ship code with AI coding tools, PRs pile up, and the
tech lead opens GitHub to 15 PRs with no idea where to start. PR Wrangler rounds them up: one
brief per PR with the line to start at, a dependency gate, and a ranked review queue, written
back to GitHub as labels, comments, and a pinned Review Queue issue. It never approves or merges.

Built as a LangSmith **Managed Deep Agent**: one orchestrator, three subagents.

| Agent | Model (Groq) | Job | Saves |
|---|---|---|---|
| orchestrator | gpt-oss-120b | Lists open PRs, delegates, publishes | |
| `review-guide` | qwen3.8-27b | One PR in depth: what it really does, the line to start at, real problems | `/briefs/<pr>.json` |
| `dependency-gate` | qwen3.8-27b | package.json changes across all PRs: duplicates, vulnerabilities, version drift, heavy deps | `/deps.json` |
| `queue-planner` | gpt-oss-120b | Review order and reasons, PRs to review together, collision advice. Code then guarantees lanes, blocked PRs, and collisions | `/queue.json` |

## Layout

```text
agent.py                    orchestrator + subagents, models
instructions.md             orchestrator instructions (full run, one-PR-changed run)
subagents/                  review_guide.py, dependency_gate.py, queue_planner.py
tools/mcp.py                GitHub MCP (read-only tools, lockdown mode)
tools/dependencies.py       dependency changes + advisories across open PRs (code, not LLM)
tools/queue_facts.py        line-level collisions between PRs + digest of saved results (code)
tools/publish.py            writes labels, comments, Start here, queue issue (code, idempotent)
tools/slack_messages.py     Slack digest + DMs to PR authors, written from the saved queue (sent via Slack MCP)
team.json                   commit author name -> Slack member ID, for DMs
middleware/tool_scope.py    gives each subagent only its own tools
middleware/stash_results.py saves subagent results as files (keeps the orchestrator's context small);
                            guards: one PR per review task, all briefs before planning; drops hallucinated findings
middleware/retries.py       retries Groq tool_use_failed; one-at-a-time review calls
channels/github.py          GitHub webhook -> run (PR events, "/wrangle" comments)
schedules/morning_queue.py  weekday 9am full run
scripts/                    local test clients and checks
```

## Run locally

```bash
uv sync
uv run mda dev --no-browser --no-reload --port 2024
uv run python scripts/ask.py "Wrangle the queue."
```

Checks against the planted answers in `../seed/expected.json`:

```bash
scripts/e2e.sh check_guide.py 1 2 3
scripts/e2e.sh check_deps.py
scripts/e2e.sh check_all.py
```

The 24 output checks live in `scripts/checks.py` (plus two run-level ones in `check_all.py`: the queue was
saved, the run didn't error). The same checks as a LangSmith dataset (`pr-wrangler-checks`) and an
experiment that scores the run saved in `../runs/`:

```bash
uv run python scripts/langsmith_evals.py              # sync the dataset + one experiment
uv run python scripts/langsmith_evals.py --sync-only  # just the dataset
```

Each experiment row shows the check, the planted answer, and the part of the agent's output it looked
at. For a fresh experiment, run `scripts/e2e.sh check_all.py` first (~11 min, a big share of Groq's
daily tokens).

`.env` needs `LANGSMITH_API_KEY`, `GROQ_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`.

Optional Slack (`#daily-pr-review` in the PR-Wrangler workspace):
- `SLACK_BOT_TOKEN` (xoxb-, bot scopes `chat:write`, `chat:write.public`, `im:write`): the orchestrator's
  `post_slack_digest` tool posts the digest and DMs **as the PR Wrangler app**.
- Without a bot token but with `SLACK_USER_TOKEN` (xoxp-, Slack MCP enabled, user scopes `chat:write`,
  `im:write`, `users:read`), it sends them through the **Slack MCP server** instead; those show up as
  the person who installed the app, because Slack MCP only accepts user tokens.
- `SLACK_DIGEST_CHANNEL` is the channel ID; `team.json` maps commit authors to Slack member IDs for DMs.
- Post on demand: `uv run python scripts/ask.py "Post the digest."` (reads the queue published in the
  Review Queue issue, so no re-run is needed). Check tokens with `uv run python scripts/check_slack.py`.
