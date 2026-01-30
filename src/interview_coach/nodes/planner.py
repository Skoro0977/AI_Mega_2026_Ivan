"""Planner node for building the interview topic plan."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import build_planner_messages, get_planner_agent
from src.interview_coach.models import ExpertRole, PlannedTopics

LOGGER = logging.getLogger(__name__)


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    model: str
    temperature: float
    max_retries: int
    planner_model: str
    planner_temperature: float
    planner_max_retries: int
    intake: Any
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]


class PlannerUpdate(TypedDict, total=False):
    """Partial state update emitted by the planner node."""

    planned_topics: list[str]
    current_topic_index: int


def run_planner(state: InterviewState) -> PlannerUpdate:
    """Generate the planned topics list if it is missing."""

    planned_topics = state.get("planned_topics") or []
    if planned_topics:
        return {}

    messages = build_planner_messages(state)
    model, temperature, max_retries = _resolve_planner_settings(state)
    agent = get_planner_agent(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Planner: start (model=%s)", model)
    result = agent.invoke({"messages": messages})
    LOGGER.info("Planner: done in %.2fs", time.monotonic() - start)

    plan = _extract_plan(result)
    return {
        "planned_topics": plan.topics,
        "current_topic_index": 0,
    }


def _resolve_planner_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("planner_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("planner_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("planner_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _extract_plan(result: Any) -> PlannedTopics:
    if isinstance(result, PlannedTopics):
        return result
    if isinstance(result, Mapping) and "structured_response" in result:
        return _coerce_plan(result["structured_response"])
    if hasattr(result, "structured_response"):
        return _coerce_plan(result.structured_response)
    return _coerce_plan(result)


def _coerce_plan(value: Any) -> PlannedTopics:
    if isinstance(value, PlannedTopics):
        return value
    if isinstance(value, BaseModel):
        return PlannedTopics.model_validate(value.model_dump())
    if isinstance(value, Mapping):
        return PlannedTopics.model_validate(dict(value))
    raise TypeError("Planner agent returned an unsupported response type.")
