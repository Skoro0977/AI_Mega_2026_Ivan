"""Expert nodes for producing internal interviewer notes."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Any, Callable, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.interview_coach.agents import build_model
from src.interview_coach.models import ExpertEvaluation, ExpertRole
from src.interview_coach.prompts import load_prompt

LOGGER = logging.getLogger(__name__)

_EXPERT_CACHE: dict[tuple[str, float, int, ExpertRole], Any] = {}

_PROMPT_BY_ROLE: dict[ExpertRole, str] = {
    ExpertRole.TECH_LEAD: "expert_tech_lead_system.md",
    ExpertRole.TEAM_LEAD: "expert_team_lead_system.md",
    ExpertRole.QA: "expert_qa_system.md",
}


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    model: str
    temperature: float
    max_retries: int
    expert_model: str
    expert_temperature: float
    expert_max_retries: int
    last_user_message: str
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]


class ExpertUpdate(TypedDict, total=False):
    """Partial state update emitted by the expert node."""

    expert_evaluations: dict[ExpertRole, str]


def create_expert_node(role: ExpertRole) -> Callable[[InterviewState], ExpertUpdate]:
    """Factory that builds an expert node for the requested role."""

    prompt_name = _PROMPT_BY_ROLE.get(role)
    if not prompt_name:
        raise ValueError(f"No prompt configured for expert role: {role}")

    def run_expert(state: InterviewState) -> ExpertUpdate:
        last_user_message = (state.get("last_user_message") or "").strip()
        if not last_user_message:
            return {}

        planned_topics = state.get("planned_topics") or []
        current_index = state.get("current_topic_index") or 0
        topic = _topic_at(planned_topics, current_index)

        messages = [
            SystemMessage(content=load_prompt(prompt_name)),
            HumanMessage(
                content=json.dumps(
                    {
                        "last_user_message": last_user_message,
                        "current_topic": topic,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ),
        ]

        model, temperature, max_retries = _resolve_expert_settings(state)
        agent = _get_expert_agent(model, temperature, max_retries, role)

        start = time.monotonic()
        LOGGER.info("Expert[%s]: start (model=%s)", role.value, model)
        result = agent.invoke({"messages": messages})
        LOGGER.info("Expert[%s]: done in %.2fs", role.value, time.monotonic() - start)

        evaluation = _extract_evaluation(result)
        text = _format_evaluation(evaluation)

        updated = dict(state.get("expert_evaluations") or {})
        updated[role] = text
        return {"expert_evaluations": updated}

    return run_expert


def _resolve_expert_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("expert_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("expert_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("expert_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _get_expert_agent(model: str, temperature: float, max_retries: int, role: ExpertRole) -> Any:
    key = (model, temperature, max_retries, role)
    if key not in _EXPERT_CACHE:
        _EXPERT_CACHE[key] = create_agent(
            build_model(model, temperature, max_retries),
            response_format=ExpertEvaluation,
        )
    return _EXPERT_CACHE[key]


def _extract_evaluation(result: Any) -> ExpertEvaluation:
    if isinstance(result, ExpertEvaluation):
        return result
    if isinstance(result, Mapping) and "structured_response" in result:
        return _coerce_evaluation(result["structured_response"])
    if hasattr(result, "structured_response"):
        return _coerce_evaluation(result.structured_response)
    return _coerce_evaluation(result)


def _coerce_evaluation(value: Any) -> ExpertEvaluation:
    if isinstance(value, ExpertEvaluation):
        return value
    if isinstance(value, BaseModel):
        return ExpertEvaluation.model_validate(value.model_dump())
    if isinstance(value, Mapping):
        return ExpertEvaluation.model_validate(dict(value))
    raise TypeError("Expert agent returned an unsupported response type.")


def _format_evaluation(evaluation: ExpertEvaluation) -> str:
    if evaluation.question:
        question = evaluation.question.strip()
        if question:
            return f"{evaluation.comment.strip()} Уточняющий вопрос: {question}"
    return evaluation.comment.strip()


def _topic_at(planned_topics: list[str], index: int) -> str | None:
    if index < 0 or index >= len(planned_topics):
        return None
    topic = planned_topics[index].strip()
    return topic or None
