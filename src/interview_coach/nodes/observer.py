"""Observer node for the interview graph."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import build_observer_messages, get_observer_agent
from src.interview_coach.models import (
    ExpertRole,
    NextAction,
    ObserverFlags,
    ObserverReport,
    ObserverRoutingDecision,
    SkillMatrix,
    TurnLog,
)

LOGGER = logging.getLogger(__name__)


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
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: int | None
    skill_matrix: SkillMatrix | dict[str, float] | None
    topics_covered: list[str] | None
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]


class ObserverUpdate(TypedDict, total=False):
    """Partial state update emitted by the observer node."""

    last_observer_report: ObserverReport
    topics_covered: list[str]
    turns: list[TurnLog]
    turn_log: TurnLog
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: int | None
    current_topic_index: int
    pending_expert_nodes: list[ExpertRole]


def run_observer(state: InterviewState) -> ObserverUpdate:
    """Evaluate the latest answer and update routing/analytics state."""

    update: ObserverUpdate = {}
    turn_log = _build_turn_log_from_pending(state)
    if turn_log is not None:
        turns = list(state.get("turns") or [])
        turns.append(turn_log)
        update["turns"] = turns
        update["turn_log"] = turn_log
        update["pending_interviewer_message"] = None
        update["pending_internal_thoughts"] = None
        update["pending_report"] = None
        update["pending_difficulty"] = None

    last_user_message = (state.get("last_user_message") or "").strip()
    if not last_user_message:
        return update

    messages = build_observer_messages(state)
    model, temperature, max_retries = _resolve_observer_settings(state)
    agent = get_observer_agent(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Observer: start (model=%s)", model)
    result = agent.invoke({"messages": messages})
    LOGGER.info("Observer: done in %.2fs", time.monotonic() - start)
    decision = _extract_decision(result)

    planned_topics = state.get("planned_topics") or []
    current_index = int(state.get("current_topic_index") or 0)
    current_topic = _topic_at(planned_topics, current_index)

    next_index = current_index
    if decision.advance_topic and planned_topics:
        next_index = min(current_index + 1, len(planned_topics))
    if next_index != current_index:
        update["current_topic_index"] = next_index

    update["pending_expert_nodes"] = decision.expert_roles

    report = _build_report(
        current_topic=current_topic,
        ask_deeper=decision.ask_deeper,
        advance_topic=decision.advance_topic,
    )
    update["last_observer_report"] = report
    update["topics_covered"] = _update_topics_covered(state.get("topics_covered"), current_topic)

    return update


def _resolve_observer_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("observer_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("observer_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("observer_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _build_turn_log_from_pending(state: InterviewState) -> TurnLog | None:
    pending_message = state.get("pending_interviewer_message")
    if not pending_message:
        return None
    user_message = state.get("last_user_message") or ""
    if not user_message.strip():
        return None
    pending_report = state.get("pending_report")
    pending_internal_thoughts = state.get("pending_internal_thoughts") or ""
    pending_difficulty = state.get("pending_difficulty")
    turns = list(state.get("turns") or [])
    turn_id = _next_turn_id(turns)
    current_topic = _topic_at(state.get("planned_topics") or [], int(state.get("current_topic_index") or 0))

    return TurnLog(
        turn_id=turn_id,
        agent_visible_message=pending_message,
        user_message=user_message,
        internal_thoughts=pending_internal_thoughts,
        topic=pending_report.detected_topic if pending_report else current_topic,
        difficulty_before=pending_difficulty,
        difficulty_after=pending_difficulty,
        flags=pending_report.flags if pending_report else None,
        skills_delta=pending_report.skills_delta if pending_report else None,
    )


def _update_topics_covered(topics: list[str] | None, detected_topic: str | None) -> list[str]:
    normalized = [topic for topic in (topics or []) if topic]
    if detected_topic:
        topic = detected_topic.strip()
        if topic and topic not in normalized:
            normalized.append(topic)
    return normalized


def _next_turn_id(turns: list[TurnLog]) -> int:
    if not turns:
        return 1
    last = turns[-1]
    return last.turn_id + 1


def _extract_decision(result: Any) -> ObserverRoutingDecision:
    if isinstance(result, ObserverRoutingDecision):
        return result
    if isinstance(result, Mapping) and "structured_response" in result:
        return _coerce_decision(result["structured_response"])
    if hasattr(result, "structured_response"):
        return _coerce_decision(result.structured_response)
    return _coerce_decision(result)


def _coerce_decision(value: Any) -> ObserverRoutingDecision:
    if isinstance(value, ObserverRoutingDecision):
        return value
    if isinstance(value, BaseModel):
        return ObserverRoutingDecision.model_validate(value.model_dump())
    if isinstance(value, Mapping):
        return ObserverRoutingDecision.model_validate(dict(value))
    raise TypeError("Observer agent returned an unsupported response type.")


def _topic_at(planned_topics: list[str], index: int) -> str | None:
    if index < 0 or index >= len(planned_topics):
        return None
    topic = planned_topics[index].strip()
    return topic or None


def _build_report(
    current_topic: str | None,
    ask_deeper: bool,
    advance_topic: bool,
) -> ObserverReport:
    action = NextAction.CHANGE_TOPIC if advance_topic else NextAction.ASK_DEEPER

    flags = ObserverFlags(
        off_topic=False,
        ask_deeper=ask_deeper,
    )

    if advance_topic:
        answer_quality = 3.8
        confidence = 0.7
    elif ask_deeper:
        answer_quality = 2.6
        confidence = 0.6
    else:
        answer_quality = 3.2
        confidence = 0.65

    return ObserverReport(
        detected_topic=current_topic or "",
        answer_quality=answer_quality,
        confidence=confidence,
        flags=flags,
        recommended_next_action=action,
        recommended_question_style="clarify" if ask_deeper else "advance",
        fact_check_notes=None,
        skills_delta=None,
    )
