"""Tests for the real-LLM agentic-loop mechanics in app.agent.llm_client,
using a scripted fake client -- no network access or ANTHROPIC_API_KEY is
needed or used. This verifies the *control flow* (dispatch a tool_use
block to the real app.tools implementation, feed the real result back,
stop when the model stops asking for tools, respect the max-turn safety
cap) independent of whether a real Claude account is configured.
"""

from dataclasses import dataclass, field
from typing import Any

from app.agent import llm_client
from app.agent.state import AgentRunState


@dataclass
class FakeBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str = "end_turn"


class ScriptedClient:
    """Returns one scripted response per call, in order."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create_message(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class TestIsAvailable:
    def test_false_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert llm_client.is_available() is False


class TestToolSchemas:
    def test_schemas_cover_every_registered_tool(self):
        from app.tools.registry import TOOL_REGISTRY

        schemas = llm_client._build_tool_schemas()
        names = {s["name"] for s in schemas}
        assert names == set(TOOL_REGISTRY)
        assert "get_production_data" in names
        assert "get_fuel_quality_data" in names
        assert "get_weather_data" in names
        assert "calculate_priority" in names

    def test_schema_marks_required_params(self):
        schemas = llm_client._build_tool_schemas()
        production = next(s for s in schemas if s["name"] == "get_production_data")
        assert set(production["input_schema"]["required"]) == {"plant", "period"}


class TestAgenticLoop:
    def test_dispatches_a_tool_call_and_stops_on_final_text(self):
        responses = [
            FakeResponse(content=[FakeBlock(type="tool_use", id="t1", name="get_production_data", input={"plant": "Plant A", "period": "FY2025-26 Q4"})]),
            FakeResponse(content=[FakeBlock(type="text", text="Plant A produced 452000 tonnes of cement.")]),
        ]
        client = ScriptedClient(responses)
        state = AgentRunState()

        llm_client.run_agentic_loop("How much cement did Plant A produce?", state, client=client)

        assert state.tools_called == ["get_production_data"]
        assert state.tool_results["get_production_data"]["status"] == "ok"
        assert state.final_answer == "Plant A produced 452000 tonnes of cement."
        assert len(client.calls) == 2

    def test_multi_turn_tool_chain(self):
        responses = [
            FakeResponse(content=[FakeBlock(type="tool_use", id="t1", name="get_emission_data", input={"plant": "Plant A", "period": "FY2025-26 Q4"})]),
            FakeResponse(content=[FakeBlock(type="tool_use", id="t2", name="get_production_data", input={"plant": "Plant A", "period": "FY2025-26 Q4"})]),
            FakeResponse(content=[FakeBlock(type="tool_use", id="t3", name="calculate_emission_intensity", input={"emissions_tco2e": 256663.7, "production_tonnes": 452000.0})]),
            FakeResponse(content=[FakeBlock(type="text", text="Plant A's emission intensity is 0.568 tCO2e/t cement.")]),
        ]
        client = ScriptedClient(responses)
        state = AgentRunState()

        llm_client.run_agentic_loop("Calculate Plant A's emission intensity.", state, client=client)

        assert state.tools_called == ["get_emission_data", "get_production_data", "calculate_emission_intensity"]
        assert state.final_answer == "Plant A's emission intensity is 0.568 tCO2e/t cement."

    def test_invalid_tool_input_is_caught_not_raised(self):
        responses = [
            FakeResponse(content=[FakeBlock(type="tool_use", id="t1", name="get_production_data", input={"plant": "Plant Z", "period": "FY2025-26 Q4"})]),
            FakeResponse(content=[FakeBlock(type="text", text="I could not find that plant.")]),
        ]
        client = ScriptedClient(responses)
        state = AgentRunState()

        llm_client.run_agentic_loop("How much cement did Plant Z produce?", state, client=client)

        assert state.tools_called == []  # the failed call is never recorded as successful
        assert any("rejected its input" in f for f in state.data_quality_flags)
        assert state.final_answer == "I could not find that plant."

    def test_stops_at_max_turns_without_fabricating_an_answer(self):
        # The model asks for a (harmless, real) tool every single turn and
        # never stops -- the loop must still terminate.
        infinite_tool_use = FakeResponse(content=[FakeBlock(type="tool_use", id="t", name="get_production_data", input={"plant": "Plant A", "period": "FY2025-26 Q4"})])
        client = ScriptedClient([infinite_tool_use] * 3)
        state = AgentRunState()

        llm_client.run_agentic_loop("Tell me everything.", state, client=client, max_turns=3)

        assert len(client.calls) == 3
        assert state.final_answer is None
        assert any("safety cap" in f for f in state.data_quality_flags)

    def test_missing_data_status_is_recorded_as_unresolved(self):
        responses = [
            FakeResponse(content=[FakeBlock(type="tool_use", id="t1", name="get_production_data", input={"plant": "Plant C", "period": "FY2025-26 Q3"})]),
            FakeResponse(content=[FakeBlock(type="text", text="Production data is missing for that period.")]),
        ]
        client = ScriptedClient(responses)
        state = AgentRunState()

        llm_client.run_agentic_loop("How much cement did Plant C produce in FY2025-26 Q3?", state, client=client)

        assert state.tool_results["get_production_data"]["status"] == "missing"
        assert any("status='missing'" in f for f in state.unresolved_questions)
