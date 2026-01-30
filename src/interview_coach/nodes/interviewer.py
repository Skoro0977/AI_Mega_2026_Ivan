"""Interviewer node for the interview graph."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
import logging
import time
from typing import Any, TypedDict

from pydantic import BaseModel
from difflib import SequenceMatcher

from src.interview_coach.agents import get_interviewer_runnable
from src.interview_coach.models import NextAction, ObserverFlags, ObserverReport, TurnLog

LOGGER = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85
MAX_REWRITE_ATTEMPTS = 2
TOPIC_SEQUENCE = (
    "python_basics",
    "async",
    "db_modeling",
    "queues",
    "observability",
    "architecture",
    "testing",
    "rag_langchain",
)
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "python_basics": ("python", "typing", "dataclass", "gil", "import"),
    "async": ("async", "await", "event loop", "coroutine", "concurrency"),
    "db_modeling": ("schema", "index", "join", "transaction", "normalization", "postgres", "sql"),
    "queues": ("queue", "kafka", "broker", "consumer", "producer", "offset", "partition"),
    "observability": ("observability", "metrics", "logging", "tracing", "otel", "opentelemetry"),
    "architecture": ("architecture", "design", "scaling", "consistency", "availability", "latency"),
    "testing": ("test", "testing", "unit", "integration", "contract"),
    "rag_langchain": ("rag", "retrieval", "embedding", "vector", "langchain", "prompt"),
}

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
    topics_covered: list[str]


def run_interviewer(state: InterviewState) -> InterviewerUpdate:
    """Generate the next interviewer message and a turn log update."""

    report = state.get("last_observer_report")
    strategy = _select_strategy(report)
    payload = _build_payload(state, report, strategy)

    model, temperature, max_retries = _resolve_interviewer_settings(state)
    runnable = get_interviewer_runnable(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Interviewer: start (model=%s)", model)
    agent_visible_message = _generate_question(runnable, payload, state)
    LOGGER.info("Interviewer: done in %.2fs", time.monotonic() - start)

    asked_questions = _update_asked_questions(state.get("asked_questions"), agent_visible_message)
    updated_topics = _update_topics_from_question(state.get("topics_covered"), agent_visible_message)

    return {
        "last_interviewer_message": agent_visible_message,
        "pending_interviewer_message": agent_visible_message,
        "pending_internal_thoughts": _build_internal_thoughts(report, strategy),
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


def _generate_question(runnable: Any, payload: dict[str, Any], state: InterviewState) -> str:
    last_user_message = (state.get("last_user_message") or "").strip()
    asked_questions = state.get("asked_questions") or []

    if _is_repeat_complaint(last_user_message):
        return _fallback_question(state.get("topics_covered"))

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

    return _fallback_question(state.get("topics_covered"))


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


def _fallback_question(topics_covered: list[str] | None) -> str:
    covered = {topic for topic in (topics_covered or []) if topic}
    next_topic = next((topic for topic in TOPIC_SEQUENCE if topic not in covered), None)
    templates = {
        "python_basics": "What Python feature do you rely on most in day-to-day backend work, and why?",
        "async": "How do you approach backpressure when using async I/O in Python?",
        "db_modeling": "How do you decide between normalization and denormalization for a read-heavy system?",
        "queues": "What trade-offs do you consider when designing Kafka partitioning?",
        "observability": "Which three signals are most important for diagnosing latency spikes, and why?",
        "architecture": "How do you evaluate trade-offs between consistency and availability in system design?",
        "testing": "How do you structure integration tests to keep them reliable and fast?",
        "rag_langchain": "How do you reduce hallucinations in a RAG system while keeping latency low?",
    }
    if next_topic and next_topic in templates:
        return templates[next_topic]
    return "Which area of backend engineering do you want to explore next?"


def _update_topics_from_question(topics: list[str] | None, question: str) -> list[str]:
    normalized = [topic for topic in (topics or []) if topic]
    detected = _infer_topic_from_question(question)
    if detected and detected not in normalized:
        normalized.append(detected)
    return normalized


def _infer_topic_from_question(question: str) -> str | None:
    text = _normalize_text(question)
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return topic
    return None


def _is_repeat_complaint(message: str) -> bool:
    text = _normalize_text(message)
    if not text:
        return False
    markers = ("повтор", "repeat", "again", "same question")
    return any(marker in text for marker in markers)


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
