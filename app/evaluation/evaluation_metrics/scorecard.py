"""Evaluation scorecard across the 8 dimensions in the project brief: tool
selection accuracy, calculation accuracy, regulatory retrieval accuracy, gap
identification accuracy, recommendation quality, data-quality handling,
handling of missing information, and end-to-end task completion.

Consumes the 10+ scenarios in `app/evaluation/test_cases/`. Implemented in
Phase 10.
"""

from typing import Any


def score_scenario(scenario: dict[str, Any], actual_outcome: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError("Implemented in Phase 10")


def build_scorecard(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    raise NotImplementedError("Implemented in Phase 10")
