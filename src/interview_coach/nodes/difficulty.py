"""Difficulty adjustment node for the interview graph."""

from __future__ import annotations

from typing import TypedDict

from src.interview_coach.models import ObserverFlags, ObserverReport


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    difficulty: int
    last_observer_report: ObserverReport | None


class DifficultyUpdate(TypedDict, total=False):
    """Partial state update emitted by the difficulty node."""

    difficulty: int


def run_difficulty(state: InterviewState) -> DifficultyUpdate:
    """Adjust difficulty based on the last observer report."""

    report = state.get("last_observer_report")
    if report is None:
        return {}

    flags = report.flags or ObserverFlags()
    if flags.role_reversal or flags.off_topic or flags.hallucination:
        return {}

    difficulty = state.get("difficulty")
    if difficulty is None:
        return {}

    updated = difficulty
    if report.answer_quality >= 4:
        updated = min(5, difficulty + 1)
    elif report.answer_quality <= 2:
        updated = max(1, difficulty - 1)

    if updated == difficulty:
        return {}

    return {"difficulty": updated}
