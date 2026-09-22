"""Declarative tool schemas: name, description, inputs, and output shape for
every agent-callable tool. `app.tools.registry` collects these into one
inventory the future planner (Phase 6) can select from without importing
every tool module by hand, and this file is what makes each tool's contract
inspectable/testable independent of its implementation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolParam:
    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    inputs: list[ToolParam]
    output_description: str
    raises: str
