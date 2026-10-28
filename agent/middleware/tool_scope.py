"""Give each subagent only the tools it needs.

MDA attaches MCP tools to the main agent, and a subagent without its own `tools`
inherits all of them. This middleware hides everything outside an allowlist before
each model call, so a subagent can't call (or spend tokens on) tools it shouldn't have.
"""

from fnmatch import fnmatch

from langchain.agents.middleware import wrap_model_call


def only_tools(*allowed: str):
    """Allowed names may be shell-style patterns, e.g. "slack_*send_message"."""
    allowed_names = set(allowed)

    def _name(tool):
        return tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)

    @wrap_model_call(name="ScopeTools")
    async def scope_tools(request, handler):
        tools = [t for t in request.tools if any(fnmatch(_name(t) or "", a) for a in allowed_names)]
        return await handler(request.override(tools=tools))

    return scope_tools
