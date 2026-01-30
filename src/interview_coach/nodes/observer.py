"""Observer node for the interview graph."""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import build_observer_messages, get_observer_agent
from src.interview_coach.models import ObserverReport, SkillMatrix, SkillTopicState


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    model: str
    temperature: float
    max_retries: int
    observer_model: str
    observer_temperature: float
    observer_max_retries: int
    messages: list[Any]
    chat_history: list[Any]
    last_interviewer_message: str
    last_user_message: str
    intake: Any
    topic: str
    difficulty: int
    turns: list[Any]
    last_observer_report: ObserverReport | None
    skill_matrix: SkillMatrix | dict[str, float] | None
    topics_covered: list[str] | None


class ObserverUpdate(TypedDict, total=False):
    """Partial state update emitted by the observer node."""

    last_observer_report: ObserverReport
    skill_matrix: SkillMatrix | dict[str, float]
    topics_covered: list[str]


def run_observer(state: InterviewState) -> ObserverUpdate:
    """Invoke the observer agent and return the partial state update."""

    messages = build_observer_messages(state)
    model, temperature, max_retries = _resolve_observer_settings(state)
    agent = get_observer_agent(model, temperature, max_retries)

    result = agent.invoke(messages)
    report = _extract_report(result)

    updated_skill_matrix = _apply_skill_delta(state.get("skill_matrix"), report.skills_delta)
    updated_topics = _update_topics_covered(state.get("topics_covered"), report.detected_topic)

    update: ObserverUpdate = {
        "last_observer_report": report,
        "topics_covered": updated_topics,
    }
    if updated_skill_matrix is not None:
        update["skill_matrix"] = updated_skill_matrix

    return update


def _resolve_observer_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("observer_model") or state.get("model") or "gpt-4o-mini")
    temperature = float(state.get("observer_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("observer_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _extract_report(result: Any) -> ObserverReport:
    if isinstance(result, ObserverReport):
        return result
    if isinstance(result, Mapping) and "structured_response" in result:
        return _coerce_report(result["structured_response"])
    if hasattr(result, "structured_response"):
        return _coerce_report(result.structured_response)
    return _coerce_report(result)


def _coerce_report(value: Any) -> ObserverReport:
    if isinstance(value, ObserverReport):
        return value
    if isinstance(value, BaseModel):
        return ObserverReport.model_validate(value.model_dump())
    if isinstance(value, Mapping):
        return ObserverReport.model_validate(dict(value))
    raise TypeError("Observer agent returned an unsupported response type.")


def _apply_skill_delta(
    skill_matrix: SkillMatrix | dict[str, float] | None,
    skills_delta: Mapping[str, float] | None,
) -> SkillMatrix | dict[str, float] | None:
    if not skills_delta:
        return skill_matrix

    if isinstance(skill_matrix, SkillMatrix):
        return _merge_skill_matrix_model(skill_matrix, skills_delta)

    merged: dict[str, float] = {}
    if isinstance(skill_matrix, dict):
        merged.update({key: float(value) for key, value in skill_matrix.items()})
    for topic, delta in skills_delta.items():
        merged[topic] = merged.get(topic, 0.0) + float(delta)
    return merged


def _merge_skill_matrix_model(
    skill_matrix: SkillMatrix,
    skills_delta: Mapping[str, float],
) -> SkillMatrix:
    updated = skill_matrix.model_copy(deep=True)
    for topic, delta in skills_delta.items():
        current = updated.topics.get(topic)
        if current is None:
            updated.topics[topic] = SkillTopicState(level_estimate=_clamp_level(delta))
            continue
        new_level = _clamp_level(current.level_estimate + float(delta))
        updated.topics[topic] = current.model_copy(update={"level_estimate": new_level})
    return updated


def _clamp_level(value: float) -> int:
    rounded = int(round(value))
    return max(1, min(5, rounded))


def _update_topics_covered(
    topics: list[str] | None, detected_topic: str | None
) -> list[str]:
    normalized = [topic for topic in (topics or []) if topic]
    if detected_topic:
        topic = detected_topic.strip()
        if topic and topic not in normalized:
            normalized.append(topic)
    return normalized
