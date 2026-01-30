"""LangGraph definition for the interview coach."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.interview_coach.models import FinalFeedback, ObserverReport, SkillMatrix, TurnLog
from src.interview_coach.nodes.difficulty import run_difficulty
from src.interview_coach.nodes.interviewer import run_interviewer
from src.interview_coach.nodes.observer import run_observer
from src.interview_coach.nodes.report import run_report
from src.interview_coach.nodes.router import route


class InterviewState(TypedDict, total=False):
    """Shared state schema for the interview graph."""

    model: str
    temperature: float
    max_retries: int
    observer_model: str
    observer_temperature: float
    observer_max_retries: int
    interviewer_model: str
    interviewer_temperature: float
    interviewer_max_retries: int
    report_model: str
    report_temperature: float
    report_max_retries: int
    stop_requested: bool
    intake: Any
    topic: str
    difficulty: int
    messages: list[Any]
    chat_history: list[Any]
    last_user_message: str
    last_interviewer_message: str
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: int | None
    last_observer_report: ObserverReport | None
    skill_matrix: SkillMatrix | dict[str, float] | None
    topics_covered: list[str]
    asked_questions: list[str]
    turns: list[TurnLog]
    observer_reports: list[Any]
    summary_notes: str
    final_feedback: FinalFeedback
    final_feedback_text: str
    turn_log: TurnLog


def _route_node(_: InterviewState) -> dict[str, Any]:
    return {}


def build_graph() -> Any:
    """Build and compile the interview StateGraph."""

    graph_builder = StateGraph(state_schema=InterviewState)

    graph_builder.add_node("router", _route_node)
    graph_builder.add_node("observer", run_observer)
    graph_builder.add_node("difficulty", run_difficulty)
    graph_builder.add_node("interviewer", run_interviewer)
    graph_builder.add_node("final_report", run_report)

    graph_builder.set_entry_point("router")

    graph_builder.add_conditional_edges(
        "router",
        route,
        {
            "final_report": "final_report",
            "observer": "observer",
        },
    )

    graph_builder.add_edge("observer", "difficulty")
    graph_builder.add_edge("difficulty", "interviewer")
    graph_builder.add_edge("interviewer", END)
    graph_builder.add_edge("final_report", END)

    return graph_builder.compile()
