"""Genuine LLM-driven tool selection: a real Claude tool-use agentic loop,
used instead of `app.agent.planner`'s rule-based classifier when
`ANTHROPIC_API_KEY` is configured (see `app.agent.orchestrator.run`).

This environment has no configured API key, so `is_available()` returns
False here and the rule-based planner runs for every test and
demonstration in this phase -- but this module is not a stub. Its control
flow (dispatch tool_use blocks, feed results back, stop when the model
stops asking for tools, cap runaway loops) is exercised in
`app/tests/test_agent_llm_client.py` against a scripted fake client, so the
mechanics are verified without needing network access or credentials.

The model is never asked to compute a number, invent plant data, or invent
a regulatory requirement -- every tool_use block is dispatched to the real
`app.tools` implementation, and the model only ever sees back what that
tool actually returned.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from app.agent.planner import parse_objective
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.state import ActivityEntry, AgentRunState, Finding
from app.calculations.errors import CalculationError
from app.tools.errors import ToolInputError
from app.tools.registry import TOOL_REGISTRY

MODEL = "claude-sonnet-5"
MAX_TURNS = 8  # hard safety cap -- the agent must not call tools indefinitely


class _ContentBlock(Protocol):
    type: str


class _AnthropicLikeResponse(Protocol):
    content: list[Any]
    stop_reason: str


class _AnthropicLikeClient(Protocol):
    def create_message(self, **kwargs: Any) -> _AnthropicLikeResponse: ...


def is_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _build_tool_schemas() -> list[dict[str, Any]]:
    schemas = []
    for spec, _fn in TOOL_REGISTRY.values():
        properties = {}
        required = []
        for p in spec.inputs:
            properties[p.name] = {"type": _json_type(p.type), "description": p.description}
            if p.required:
                required.append(p.name)
        schemas.append({
            "name": spec.name,
            "description": spec.description,
            "input_schema": {"type": "object", "properties": properties, "required": required},
        })
    return schemas


def _json_type(python_type_label: str) -> str:
    return {
        "str": "string",
        "float": "number",
        "int": "integer",
        "dict": "object",
        "list[dict]": "array",
        "list[str]": "array",
    }.get(python_type_label, "string")


def _dispatch_tool(state: AgentRunState, name: str, tool_input: dict[str, Any]) -> Any:
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool {name!r}"}
    _, fn = TOOL_REGISTRY[name]
    try:
        result = fn(**tool_input)
    except (ToolInputError, CalculationError) as exc:
        state.data_quality_flags.append(f"{name} rejected its input: {exc}")
        state.activity_trace.append(ActivityEntry("tool_called", f"{name} could not run: {exc}", status="blocked"))
        return {"error": str(exc)}

    state.tools_called.append(name)
    state.tool_results[name] = result
    status = result.get("status") if isinstance(result, dict) else None
    activity_status = "warning" if status in ("missing", "conflict") else "done"
    state.activity_trace.append(ActivityEntry("tool_called", f"Called {name} -> status={status}", activity_status))
    if status in ("missing", "conflict"):
        state.unresolved_questions.append(f"{name} returned status='{status}'.")
    return result


def _make_real_client() -> _AnthropicLikeClient:
    import anthropic

    sdk_client = anthropic.Anthropic()

    class _RealClientAdapter:
        def create_message(self, **kwargs: Any) -> Any:
            return sdk_client.messages.create(**kwargs)

    return _RealClientAdapter()


def get_client() -> _AnthropicLikeClient:
    """Public factory for a real Claude client, for other modules that want
    to reuse the same minimal `create_message(...)` interface this module
    defines (e.g. `app.compliance.gap_analysis`'s optional LLM-assisted
    root-cause exploration) without reaching into a private helper. Callers
    should check `is_available()` first."""
    return _make_real_client()


def run_agentic_loop(
    raw_query: str,
    state: AgentRunState,
    plant_hint: str | None = None,
    period_hint: str | None = None,
    client: _AnthropicLikeClient | None = None,
    max_turns: int = MAX_TURNS,
) -> None:
    """Run the real Claude tool-use loop, mutating `state` as tools are
    called. `client` is injectable so tests can supply a scripted fake
    instead of hitting the network -- see test_agent_llm_client.py.
    """
    from app.data.constants import PERIODS, PLANTS

    objective = parse_objective(raw_query, plant_hint, period_hint)
    state.objective = objective
    state.activity_trace.append(ActivityEntry("objective_understood", f"Objective identified: {objective.desired_output}"))
    for a in objective.assumptions:
        state.findings.append(Finding("Assumption", a))

    client = client or _make_real_client()
    tools = _build_tool_schemas()
    system = AGENT_SYSTEM_PROMPT.format(plants=", ".join(PLANTS), periods=", ".join(PERIODS))
    messages: list[dict[str, Any]] = [{"role": "user", "content": raw_query}]

    for turn in range(max_turns):
        response = client.create_message(
            model=MODEL, max_tokens=1024, system=system, messages=messages, tools=tools,
        )
        tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]

        if not tool_use_blocks:
            state.final_answer = " ".join(b.text for b in text_blocks).strip() or None
            state.plan.append(f"Model stopped requesting tools after {turn} tool-use turn(s).")
            return

        messages.append({"role": "assistant", "content": response.content})
        tool_results_content = []
        for block in tool_use_blocks:
            result = _dispatch_tool(state, block.name, block.input)
            tool_results_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results_content})

    state.data_quality_flags.append(f"Stopped after reaching the {max_turns}-turn safety cap without a final answer.")
    state.final_answer = None
