"""Queue planner: turns the briefs, dependency flags, and line-level collisions into a review order.

The planner gets no tools. Its facts are computed in code and handed to it in the prompt,
and it answers with Groq's native JSON-schema mode. (With a tool-based structured output,
gpt-oss-120b kept writing the queue as plain text instead of calling the tool.)

The model writes the judgment: order within each lane, reasons, review-together groups,
collision advice, and the headline. Code (finalize_queue) guarantees the facts afterwards:
lanes, every PR exactly once, blocked PRs, and collisions.
"""

from typing import Literal

from langchain.agents.middleware import wrap_model_call
from langchain.agents.structured_output import ProviderStrategy
from langchain.messages import HumanMessage
from pydantic import BaseModel, Field

from middleware.retries import groq_tool_retry
from middleware.tool_scope import only_tools
from tools.queue_facts import compute_queue_facts


class QueueItem(BaseModel):
    pr: int
    lane: Literal["quick-win", "review", "fix-first", "blocked"]
    reason: str = Field(description="Why it sits here, in under 15 words.")


class Group(BaseModel):
    prs: list[int]
    why: str = Field(description="Under 15 words.")


class Collision(BaseModel):
    prs: list[int]
    file: str
    advice: str = Field(description="Which to merge first, or what to decide, in under 20 words.")


class Blocked(BaseModel):
    pr: int
    waits_for: int
    why: str = Field(description="Under 15 words.")


class ReviewQueue(BaseModel):
    headline: str = Field(description="One sentence the tech lead reads first, e.g. '15 open: 4 quick wins, ...'.")
    order: list[QueueItem] = Field(description="Every open PR exactly once, in the order to review them.")
    # Defaults: if the model drops a list, finalize_queue (tools/queue_facts.py) fills in what code knows.
    review_together: list[Group] = Field(default_factory=list)
    collisions: list[Collision] = Field(default_factory=list)
    blocked: list[Blocked] = Field(default_factory=list)


PROMPT = """\
You plan the review queue for the GitHub repo dhanush014/tiny-todo. A tech lead faces about 15
open PRs from seven developers. Give them an order that gets the most merged with the least effort
and no surprises.

The last message holds the facts as JSON: every open PR's size, files, base branch (stacked_on),
a digest of its review brief, its dependency flags, and which PRs collide. Return a ReviewQueue.

Lanes are already decided: every PR in the facts has a `lane`. Copy it exactly; never change it.
- quick-win: tiny, clean, low risk. Merge these first.
- review: needs a real review.
- fix-first: has a bug or a vulnerable/duplicate dependency. It goes back to the author first;
  the reason names the problem.
- blocked: stacked on another open PR.

Order: all quick-win PRs first (smallest first), then review (PRs that unblock others or that should
win a collision first), then fix-first, then blocked last.

Reasons: specific and under 15 words, e.g. "inverted filter deletes active to-dos" or "one-line typo fix".

review_together: go through review_together_candidates. Keep a pair when, judging by the titles,
both PRs build the same feature or the same part of the UI (for example two new footer controls, or
two celebrations using the same package). Drop pairs that only happen to touch neighbouring lines.
Collisions alone are not a reason to review together.

collisions: every pair in collisions_same_lines. Say which PR should merge first and what the other
author has to redo. Ignore append-to-end and same-spot conflicts here; mention them in the headline
only if many PRs have them.

Every open PR appears in `order` exactly once.
"""


@wrap_model_call(name="InjectQueueFacts")
async def inject_queue_facts(request, handler):
    """Compute the facts in code and add them to the planner's prompt."""
    files = (request.state or {}).get("files") or {}
    facts = await compute_queue_facts(files)
    messages = [*request.messages, HumanMessage(content=f"Facts:\n{facts}")]
    return await handler(request.override(messages=messages))


queue_planner = {
    "name": "queue-planner",
    "description": (
        "Plans the review order for ALL open PRs: lanes (quick-win, review, fix-first, blocked), "
        "PRs to review together, PRs that edit the same lines, and blocked PRs. "
        "Run it once, AFTER every review brief and the dependency report are saved."
    ),
    "system_prompt": PROMPT,
    "response_format": ProviderStrategy(ReviewQueue),
    "middleware": [only_tools(), inject_queue_facts, groq_tool_retry()],
}
