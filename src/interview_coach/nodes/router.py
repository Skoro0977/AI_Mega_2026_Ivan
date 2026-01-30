"""Routing node for the interview graph."""

from __future__ import annotations

from typing import Literal, TypedDict

from src.interview_coach.models import ObserverReport


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    stop_requested: bool
    last_observer_report: ObserverReport | None


NodeName = Literal["final_report", "observer", "difficulty", "interviewer"]


def route(state: InterviewState) -> NodeName:
    """Return the next node name based on the current state."""

    if state.get("stop_requested"):
        return "final_report"

    report = state.get("last_observer_report")
    if report is None:
        return "observer"

    return "difficulty"
