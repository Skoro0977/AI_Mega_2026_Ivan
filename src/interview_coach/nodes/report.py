"""Final report node for the interview graph."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import build_report_messages, get_report_agent
from src.interview_coach.models import ExpertRole, FinalFeedback, GradeTarget

LOGGER = logging.getLogger(__name__)


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    model: str
    temperature: float
    max_retries: int
    report_model: str
    report_temperature: float
    report_max_retries: int
    intake: Any
    skill_matrix: Any
    turns: list[Any]
    observer_reports: list[Any]
    summary_notes: str
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]
    topics_covered: list[str]


class ReportUpdate(TypedDict, total=False):
    """Partial state update emitted by the report node."""

    final_feedback: FinalFeedback
    final_feedback_text: str


def run_report(state: InterviewState) -> ReportUpdate:
    """Invoke the report agent and return final feedback."""

    messages = build_report_messages(state)
    model, temperature, max_retries = _resolve_report_settings(state)
    agent = get_report_agent(model, temperature, max_retries)

    start = time.monotonic()
    LOGGER.info("Report: start (model=%s)", model)
    result = agent.invoke({"messages": messages})
    LOGGER.info("Report: done in %.2fs", time.monotonic() - start)
    feedback = _extract_feedback(result)

    update: ReportUpdate = {"final_feedback": feedback}
    summary = _summarize_feedback(feedback)
    if summary:
        update["final_feedback_text"] = summary
    metrics = _collect_feedback_metrics(feedback, state)
    LOGGER.info("Final feedback metrics: %s", metrics)

    return update


def _resolve_report_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("report_model") or state.get("model") or "gpt-5-nano")
    temperature = float(state.get("report_temperature") or state.get("temperature") or 0.2)
    max_retries = int(state.get("report_max_retries") or state.get("max_retries") or 2)
    return model, temperature, max_retries


def _extract_feedback(result: Any) -> FinalFeedback:
    if isinstance(result, FinalFeedback):
        return result
    if isinstance(result, Mapping) and "structured_response" in result:
        return _coerce_feedback(result["structured_response"])
    if hasattr(result, "structured_response"):
        return _coerce_feedback(result.structured_response)
    return _coerce_feedback(result)


def _coerce_feedback(value: Any) -> FinalFeedback:
    if isinstance(value, FinalFeedback):
        return value
    if isinstance(value, BaseModel):
        return FinalFeedback.model_validate(value.model_dump())
    if isinstance(value, Mapping):
        return FinalFeedback.model_validate(dict(value))
    raise TypeError("Report agent returned an unsupported response type.")


def _summarize_feedback(feedback: FinalFeedback) -> str:
    decision = feedback.decision
    hard = feedback.hard_skills
    soft = feedback.soft_skills
    roadmap = feedback.roadmap

    parts: list[str] = []
    grade_label = _grade_label(decision.grade)
    parts.append(f"В целом вы уверенно тянете уровень {grade_label}.")
    if hard.confirmed:
        parts.append("Видно, что у вас есть реальный практический опыт: " + _join_items(hard.confirmed) + ".")
    if soft.clarity or soft.honesty or soft.engagement:
        soft_bits = [bit for bit in [soft.clarity, soft.honesty, soft.engagement] if bit]
        if soft_bits:
            parts.append("По софт-скиллам: " + " ".join(soft_bits).rstrip(".") + ".")
    if soft.examples:
        parts.append("Примеры: " + _join_items(soft.examples) + ".")
    if hard.gaps_with_correct_answers:
        gaps_text = "; ".join(
            f"{gap} — {answer}".rstrip(".")
            for gap, answer in hard.gaps_with_correct_answers.items()
        )
        parts.append("Что можно усилить: " + gaps_text + ".")
    if roadmap.next_steps:
        parts.append("Рекомендации на следующий шаг: " + _join_items(roadmap.next_steps) + ".")
    if decision.recommendation:
        parts.append("Общая рекомендация: " + decision.recommendation.rstrip(".") + ".")
    confidence_pct = int(round(decision.confidence_score * 100))
    parts.append(f"Уверенность в оценке — примерно {confidence_pct}%.")

    return "\n\n".join(parts).strip()


_MESSAGE_REF_RE = re.compile(r"сообщен(?:ие|ия|ии)\s*№\s*(\d+)", re.IGNORECASE)


def _collect_feedback_metrics(feedback: FinalFeedback, state: Mapping[str, Any]) -> dict[str, Any]:
    decision = feedback.decision
    hard = feedback.hard_skills
    soft = feedback.soft_skills
    roadmap = feedback.roadmap

    confirmed = [_collect_item_metrics(item) for item in hard.confirmed]
    gaps = [
        {
            "gap": gap,
            "answer": answer,
            "message_ids": _extract_message_ids(f"{gap} {answer}"),
        }
        for gap, answer in hard.gaps_with_correct_answers.items()
    ]
    examples = [_collect_item_metrics(item) for item in soft.examples]
    next_steps = [_collect_item_metrics(item) for item in roadmap.next_steps]

    message_ids: set[int] = set()
    for collection in (confirmed, gaps, examples, next_steps):
        for item in collection:
            message_ids.update(item.get("message_ids", []))

    turns = state.get("turns") or []
    observer_reports = state.get("observer_reports") or []

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_model": state.get("report_model") or state.get("model"),
        "grade": decision.grade.value if isinstance(decision.grade, GradeTarget) else str(decision.grade),
        "confidence_score": decision.confidence_score,
        "recommendation": decision.recommendation,
        "counts": {
            "confirmed": len(hard.confirmed),
            "gaps": len(hard.gaps_with_correct_answers),
            "examples": len(soft.examples),
            "next_steps": len(roadmap.next_steps),
            "turns": len(turns),
            "observer_reports": len(observer_reports),
        },
        "message_sources": sorted(message_ids),
        "evidence": {
            "confirmed": confirmed,
            "gaps": gaps,
            "examples": examples,
            "next_steps": next_steps,
        },
        "topics_covered": state.get("topics_covered") or [],
    }


def _extract_message_ids(text: str) -> list[int]:
    return sorted({int(match.group(1)) for match in _MESSAGE_REF_RE.finditer(text)})


def _collect_item_metrics(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "message_ids": _extract_message_ids(text),
    }


def _grade_label(grade: GradeTarget | Any) -> str:
    if isinstance(grade, GradeTarget):
        value = grade.value
    else:
        value = str(grade)
    mapping = {
        "intern": "intern-разработчика",
        "junior": "junior-разработчика",
        "middle": "middle-разработчика",
        "senior": "senior-разработчика",
        "staff": "staff-разработчика",
        "principal": "principal-разработчика",
    }
    return mapping.get(value, value)


def _join_items(items: list[str]) -> str:
    return "; ".join(item.strip().rstrip(".") for item in items if item and item.strip())
