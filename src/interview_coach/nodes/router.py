"""Routing node for the interview graph."""

from __future__ import annotations

from typing import Literal, TypedDict


class InterviewState(TypedDict, total=False):
    """State payload passed through the interview graph."""

    stop_requested: bool
    last_user_message: str
    pending_interviewer_message: str | None


NodeName = Literal["final_report", "observer", "interviewer"]


def route(state: InterviewState) -> NodeName:
    """Return the next node name based on the current state."""

    if state.get("stop_requested"):
        return "final_report"

    last_user_message = (state.get("last_user_message") or "").strip()
    pending_interviewer_message = state.get("pending_interviewer_message")
    if not last_user_message and not pending_interviewer_message:
        return "interviewer"

    return "observer"
