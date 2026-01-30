"""Difficulty adjustment node for the interview graph."""

from __future__ import annotations

import logging
from typing import TypedDict

from src.interview_coach.models import ExpertRole, ObserverFlags, ObserverReport

LOGGER = logging.getLogger(__name__)


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    difficulty: str
    last_observer_report: ObserverReport | None
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]


class DifficultyUpdate(TypedDict, total=False):
    """Partial state update emitted by the difficulty node."""

    difficulty: str
    difficulty_reason: str


def run_difficulty(state: InterviewState) -> DifficultyUpdate:
    """Adjust difficulty based on the last observer report."""

    LOGGER.info("Difficulty: start")
    report = state.get("last_observer_report")
    if report is None:
        LOGGER.info("Difficulty: skip (no report)")
        return {}

    flags = report.flags or ObserverFlags()
    if flags.role_reversal or flags.off_topic or flags.hallucination:
        LOGGER.info("Difficulty: skip (flags=%s)", flags.model_dump())
        return {}

    difficulty = (state.get("difficulty") or "").strip().upper()
    if not difficulty:
        LOGGER.info("Difficulty: skip (no difficulty)")
        return {}

    order = ("EASY", "MEDIUM", "HARD")
    if difficulty not in order:
        LOGGER.info("Difficulty: skip (unknown=%s)", difficulty)
        return {}

    idx = order.index(difficulty)
    updated = difficulty
    reason = ""
    if report.answer_quality >= 4.0:
        updated = order[min(len(order) - 1, idx + 1)]
        reason = f"increase (answer_quality={report.answer_quality:.2f})"
    elif report.answer_quality <= 2.0:
        updated = order[max(0, idx - 1)]
        reason = f"decrease (answer_quality={report.answer_quality:.2f})"

    if updated == difficulty:
        LOGGER.info("Difficulty: unchanged (%s)", difficulty)
        return {"difficulty_reason": ""}

    LOGGER.info("Difficulty: updated %s -> %s", difficulty, updated)
    return {"difficulty": updated, "difficulty_reason": reason}
