"""Interviewer node for the interview graph."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import get_interviewer_runnable
from src.interview_coach.models import ExpertRole, NextAction, ObserverFlags, ObserverReport, TurnLog

LOGGER = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85
MAX_REWRITE_ATTEMPTS = 2


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
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]
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
    topics_covered: list[str]


def run_interviewer(state: InterviewState) -> InterviewerUpdate:
    """Generate the next interviewer message and a turn log update."""

    report = state.get("last_observer_report")
    strategy = _select_strategy(report, state.get("last_user_message"))
    payload = _build_payload(state, report, strategy)

    model, temperature, max_retries = _resolve_interviewer_settings(state)
    runnable = get_interviewer_runnable(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Interviewer: start (model=%s)", model)
    agent_visible_message = _generate_message(runnable, payload, state)
    LOGGER.info("Interviewer: done in %.2fs", time.monotonic() - start)

    asked_questions = _update_asked_questions(state.get("asked_questions"), agent_visible_message)
    updated_topics = _update_topics_from_plan(state.get("topics_covered"), state)

    return {
        "last_interviewer_message": agent_visible_message,
        "pending_interviewer_message": agent_visible_message,
        "pending_internal_thoughts": _build_internal_thoughts(
            report,
            strategy,
            state.get("expert_evaluations"),
        ),
        "pending_report": report,
        "pending_difficulty": state.get("difficulty"),
        "asked_questions": asked_questions,
        "topics_covered": updated_topics,
    }


def _resolve_interviewer_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("interviewer_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("interviewer_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("interviewer_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _select_strategy(report: ObserverReport | None, last_user_message: str | None) -> str:
    if report is None:
        if last_user_message and _looks_like_question(last_user_message):
            return "answer_candidate_question"
        return "ask_standard"

    action = report.recommended_next_action
    if action == NextAction.HANDLE_ROLE_REVERSAL:
        return "return_roles"
    if action == NextAction.HANDLE_HALLUCINATION:
        return "challenge_hallucination"
    if action == NextAction.HANDLE_OFFTOPIC:
        return "return_to_topic"
    flags = report.flags or ObserverFlags()
    if flags.role_reversal:
        return "return_roles"
    if flags.hallucination:
        return "challenge_hallucination"
    if flags.off_topic:
        return "return_to_topic"

    if action == NextAction.ASK_DEEPER:
        return "deepen"
    if action == NextAction.CHANGE_TOPIC:
        return "change_topic"
    if action == NextAction.WRAP_UP:
        return "wrap_up"
    return "ask_standard"


def _build_payload(
    state: InterviewState,
    report: ObserverReport | None,
    strategy: str,
) -> dict[str, Any]:
    planned_topics = state.get("planned_topics") or []
    current_topic_index = int(state.get("current_topic_index") or 0)
    current_topic = _topic_at(planned_topics, current_topic_index)
    next_topic = _topic_at(planned_topics, current_topic_index + 1)
    expert_evaluations = _serialize(state.get("expert_evaluations")) or {}
    ask_deeper = bool(report.flags.ask_deeper) if report and report.flags else False
    advance_topic = report.recommended_next_action == NextAction.CHANGE_TOPIC if report else False

    payload: dict[str, Any] = {
        "intake": _serialize(state.get("intake")),
        "observer_report": _serialize(report),
        "observer_decision": {
            "ask_deeper": ask_deeper,
            "advance_topic": advance_topic,
        },
        "skill_matrix": _serialize(state.get("skill_matrix")),
        "recent_turns": _serialize(_tail(state.get("turns"))),
        "last_user_message": state.get("last_user_message") or "",
        "last_interviewer_message": state.get("last_interviewer_message") or "",
        "strategy": strategy,
        "difficulty": state.get("difficulty"),
        "topics_covered": state.get("topics_covered") or [],
        "asked_questions": state.get("asked_questions") or [],
        "planned_topics": planned_topics,
        "current_topic_index": current_topic_index,
        "current_topic": current_topic,
        "next_topic": next_topic,
        "expert_evaluations": expert_evaluations,
    }
    return payload


def _generate_message(runnable: Any, payload: dict[str, Any], state: InterviewState) -> str:
    last_user_message = (state.get("last_user_message") or "").strip()
    asked_questions = state.get("asked_questions") or []

    base = runnable.invoke({"context": json.dumps(payload, ensure_ascii=False)})
    if not _is_duplicate(base, asked_questions):
        return base

    avoid = _tail(asked_questions, limit=12)
    for _ in range(MAX_REWRITE_ATTEMPTS):
        rewrite_payload = dict(payload)
        rewrite_payload["rewrite_instructions"] = (
            "Rewrite the question to avoid repeating the listed questions/topics. "
            "Ask a new question on a different topic if needed."
        )
        rewrite_payload["avoid_questions"] = avoid
        rewrite_payload["avoid_topics"] = payload.get("topics_covered") or []
        candidate = runnable.invoke({"context": json.dumps(rewrite_payload, ensure_ascii=False)})
        if not _is_duplicate(candidate, asked_questions):
            return candidate

    return base


def _is_duplicate(candidate: str, asked_questions: list[str]) -> bool:
    normalized_candidate = _normalize_text(candidate)
    if not normalized_candidate:
        return False
    for asked in asked_questions:
        if _similarity_ratio(normalized_candidate, _normalize_text(asked)) >= SIMILARITY_THRESHOLD:
            return True
    return False


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9а-яё\s]", " ", lowered)
    collapsed = re.sub(r"\s+", " ", cleaned).strip()
    return collapsed


def _similarity_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _update_topics_from_plan(topics: list[str] | None, state: InterviewState) -> list[str]:
    normalized = [topic for topic in (topics or []) if topic]
    current_topic = _topic_at(state.get("planned_topics") or [], int(state.get("current_topic_index") or 0))
    if current_topic and current_topic not in normalized:
        normalized.append(current_topic)
    return normalized


def _is_repeat_complaint(message: str) -> bool:
    text = _normalize_text(message)
    if not text:
        return False
    markers = ("повтор", "repeat", "again", "same question")
    return any(marker in text for marker in markers)


def _build_internal_thoughts(
    report: ObserverReport | None,
    strategy: str,
    expert_evaluations: dict[ExpertRole, str] | None,
) -> str:
    parts: list[str] = []
    if report is None:
        parts.append("[Observer]: no report.")
    else:
        flags = report.flags
        flags_summary = (
            f"off_topic={flags.off_topic}, hallucination={flags.hallucination}, "
            f"contradiction={flags.contradiction}, role_reversal={flags.role_reversal}, "
            f"ask_deeper={flags.ask_deeper}"
        )
        observer_summary = (
            f"topic={report.detected_topic}, next_action={report.recommended_next_action}, {flags_summary}"
        )
        parts.append(f"[Observer]: {observer_summary}.")

    parts.extend(_format_expert_thoughts(expert_evaluations))
    parts.append(f"[Interviewer]: strategy={strategy}.")
    return " ".join(parts)


def _format_expert_thoughts(expert_evaluations: dict[ExpertRole, str] | None) -> list[str]:
    if not expert_evaluations:
        return []
    entries: list[tuple[str, str]] = []
    for role, text in expert_evaluations.items():
        role_name = role.value if isinstance(role, ExpertRole) else str(role)
        cleaned = str(text).strip()
        if cleaned:
            entries.append((role_name, cleaned))
    entries.sort(key=lambda item: item[0])
    return [f"[Expert:{role}]: {text}." for role, text in entries]


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


def _looks_like_question(text: str) -> bool:
    if "?" in text:
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in ("что", "почему", "как", "когда", "зачем", "можно ли"))


def _topic_at(planned_topics: list[str], index: int) -> str | None:
    if index < 0 or index >= len(planned_topics):
        return None
    topic = planned_topics[index].strip()
    return topic or None
