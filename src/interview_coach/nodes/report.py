"""Final report node for the interview graph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from pydantic import BaseModel

from src.interview_coach.agents import build_report_messages, get_report_agent
from src.interview_coach.models import FinalFeedback


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


class ReportUpdate(TypedDict, total=False):
    """Partial state update emitted by the report node."""

    final_feedback: FinalFeedback
    final_feedback_text: str


def run_report(state: InterviewState) -> ReportUpdate:
    """Invoke the report agent and return final feedback."""

    messages = build_report_messages(state)
    model, temperature, max_retries = _resolve_report_settings(state)
    agent = get_report_agent(model, temperature, max_retries)

    result = agent.invoke({"messages": messages})
    feedback = _extract_feedback(result)

    update: ReportUpdate = {"final_feedback": feedback}
    summary = _summarize_feedback(feedback)
    if summary:
        update["final_feedback_text"] = summary

    return update


def _resolve_report_settings(state: Mapping[str, Any]) -> tuple[str, float, int]:
    model = str(state.get("report_model") or state.get("model") or "gpt-4o-mini")
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

    parts = [
        f"Grade: {decision.grade}.",
        f"Recommendation: {decision.recommendation}.",
        f"Confidence: {decision.confidence_score:.2f}.",
    ]
    if hard.confirmed:
        parts.append("Confirmed: " + "; ".join(hard.confirmed) + ".")
    if hard.gaps_with_correct_answers:
        gaps = ", ".join(hard.gaps_with_correct_answers.keys())
        parts.append("Gaps: " + gaps + ".")
    if soft.examples:
        parts.append("Examples: " + "; ".join(soft.examples) + ".")
    if roadmap.next_steps:
        parts.append("Next steps: " + "; ".join(roadmap.next_steps) + ".")

    return " ".join(parts)
