"""Routing node for the interview graph."""

from __future__ import annotations

from typing import Literal, TypedDict


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    stop_requested: bool


NodeName = Literal["final_report", "observer", "difficulty", "interviewer"]


def route(state: InterviewState) -> NodeName:
    """Return the next node name based on the current state."""

    if state.get("stop_requested"):
        return "final_report"

    return "observer"
