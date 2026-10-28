"""Retry Groq's flaky 400s.

Models on Groq sometimes return an answer Groq itself can't parse (400 tool_use_failed when
a tool call is required, 400 output_parse_failed otherwise). A fresh attempt almost always
works, so retry those instead of failing the whole run. Rate limits (429) are already
retried by the ChatGroq client.
"""

import asyncio

import groq
from langchain.agents.middleware import ModelRetryMiddleware, wrap_model_call


FLAKY = ("tool_use_failed", "output_parse_failed")


def _is_flaky_400(error: Exception) -> bool:
    return isinstance(error, groq.BadRequestError) and any(code in str(error) for code in FLAKY)


def groq_tool_retry():
    return ModelRetryMiddleware(max_retries=3, retry_on=_is_flaky_400, on_failure="error")


def one_at_a_time(name: str):
    """Run this subagent's model calls one at a time across parallel delegations.

    The orchestrator may hand out 15 reviews at once; sending them all to one Groq
    model at the same moment just turns into a wall of 429s.
    """
    lock = asyncio.Semaphore(1)

    @wrap_model_call(name=f"OneAtATime_{name}")
    async def serialize(request, handler):
        async with lock:
            return await handler(request)

    return serialize
