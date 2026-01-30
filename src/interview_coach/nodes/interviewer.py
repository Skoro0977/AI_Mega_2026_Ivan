"""Interviewer node for the interview graph."""

from __future__ import annotations

import json
from collections.abc import Mapping
import logging
import time
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import get_interviewer_runnable
from src.interview_coach.models import NextAction, ObserverFlags, ObserverReport, TurnLog

LOGGER = logging.getLogger(__name__)

class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    model: str
    temperature: float
    max_retries: int
    interviewer_model: str
    interviewer_temperature: float
    interviewer_max_retries: int
    last_user_message: str
    last_interviewer_message: str
    last_observer_report: ObserverReport | None
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: int | None
    turns: list[TurnLog]
    difficulty: int
    topics_covered: list[str]
    asked_questions: list[str]
    intake: Any
    skill_matrix: Any


class InterviewerUpdate(TypedDict, total=False):
    """Partial state update emitted by the interviewer node."""

    last_interviewer_message: str
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: int | None
    asked_questions: list[str]


def run_interviewer(state: InterviewState) -> InterviewerUpdate:
    """Generate the next interviewer message and a turn log update."""

    report = state.get("last_observer_report")
    strategy = _select_strategy(report)
    payload = _build_payload(state, report, strategy)

    model, temperature, max_retries = _resolve_interviewer_settings(state)
    runnable = get_interviewer_runnable(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Interviewer: start (model=%s)", model)
    agent_visible_message = runnable.invoke({"context": json.dumps(payload, ensure_ascii=False)})
    LOGGER.info("Interviewer: done in %.2fs", time.monotonic() - start)

    asked_questions = _update_asked_questions(state.get("asked_questions"), agent_visible_message)

    return {
        "last_interviewer_message": agent_visible_message,
        "pending_interviewer_message": agent_visible_message,
        "pending_internal_thoughts": _build_internal_thoughts(report, strategy),
        "pending_report": report,
        "pending_difficulty": state.get("difficulty"),
        "asked_questions": asked_questions,
    }


def _resolve_interviewer_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("interviewer_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("interviewer_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("interviewer_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _select_strategy(report: ObserverReport | None) -> str:
    if report is None:
        return "ask_standard"

    flags = report.flags or ObserverFlags()
    if flags.role_reversal:
        return "answer_candidate_question"
    if flags.off_topic:
        return "return_to_topic"
    if flags.hallucination:
        return "handle_hallucination"

    action = report.recommended_next_action
    if action == NextAction.ASK_DEEPER:
        return "deepen"
    if action == NextAction.ASK_EASIER:
        return "simplify"
    if action == NextAction.CHANGE_TOPIC:
        return "change_topic"
    if action == NextAction.HANDLE_OFFTOPIC:
        return "return_to_topic"
    if action == NextAction.HANDLE_HALLUCINATION:
        return "handle_hallucination"
    if action == NextAction.HANDLE_ROLE_REVERSAL:
        return "answer_candidate_question"
    if action == NextAction.WRAP_UP:
        return "wrap_up"
    return "ask_standard"


def _build_payload(
    state: InterviewState,
    report: ObserverReport | None,
    strategy: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "intake": _serialize(state.get("intake")),
        "observer_report": _serialize(report),
        "skill_matrix": _serialize(state.get("skill_matrix")),
        "recent_turns": _serialize(_tail(state.get("turns"))),
        "last_user_message": state.get("last_user_message") or "",
        "last_interviewer_message": state.get("last_interviewer_message") or "",
        "strategy": strategy,
        "difficulty": state.get("difficulty"),
        "topics_covered": state.get("topics_covered") or [],
        "asked_questions": state.get("asked_questions") or [],
    }
    return payload


def _build_internal_thoughts(report: ObserverReport | None, strategy: str) -> str:
    if report is None:
        return f"[Observer]: no report. [Interviewer]: strategy={strategy}."
    flags = report.flags
    flags_summary = (
        f"off_topic={flags.off_topic}, hallucination={flags.hallucination}, "
        f"contradiction={flags.contradiction}, role_reversal={flags.role_reversal}"
    )
    observer_summary = f"topic={report.detected_topic}, next_action={report.recommended_next_action}, {flags_summary}"
    return f"[Observer]: {observer_summary}. [Interviewer]: strategy={strategy}."


def _update_asked_questions(asked: list[str] | None, message: str) -> list[str]:
    normalized = [item for item in (asked or []) if item]
    cleaned = message.strip()
    if cleaned and cleaned not in normalized:
        normalized.append(cleaned)
    return normalized


def _tail(value: Any, limit: int = 5) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value[-limit:]
    return [value]


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
