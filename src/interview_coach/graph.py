"""LangGraph definition for the interview coach."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.interview_coach.models import ExpertRole, FinalFeedback, NextAction, ObserverReport, SkillMatrix, TurnLog
from src.interview_coach.nodes.difficulty import run_difficulty
from src.interview_coach.nodes.experts import create_expert_node
from src.interview_coach.nodes.interviewer import run_interviewer
from src.interview_coach.nodes.observer import run_observer
from src.interview_coach.nodes.planner import run_planner
from src.interview_coach.nodes.report import run_report


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
    planner_model: str
    planner_temperature: float
    planner_max_retries: int
    expert_model: str
    expert_temperature: float
    expert_max_retries: int
    report_model: str
    report_temperature: float
    report_max_retries: int
    stop_requested: bool
    intake: Any
    topic: str
    difficulty: str
    difficulty_reason: str
    messages: list[Any]
    chat_history: list[Any]
    last_user_message: str
    last_interviewer_message: str
    pending_interviewer_message: str | None
    pending_internal_thoughts: str | None
    pending_report: ObserverReport | None
    pending_difficulty: str | None
    pending_difficulty_reason: str | None
    last_observer_report: ObserverReport | None
    skill_matrix: SkillMatrix | dict[str, float] | None
    topics_covered: list[str]
    asked_questions: list[str]
    planned_topics: list[str]
    current_topic_index: int
    expert_evaluations: dict[ExpertRole, str]
    pending_expert_nodes: list[ExpertRole]
    turns: list[TurnLog]
    observer_reports: list[Any]
    summary_notes: str
    final_feedback: FinalFeedback
    final_feedback_text: str
    turn_log: TurnLog


def _route_after_observer(state: InterviewState) -> str:
    if _should_finalize(state):
        return "final_report"
    if state.get("pending_expert_nodes"):
        return "experts_router"
    return "difficulty"


def _route_experts(state: InterviewState) -> str:
    pending = state.get("pending_expert_nodes") or []
    if not pending:
        return "difficulty"
    role = pending[0]
    return _EXPERT_NODES.get(role, "difficulty")


def _should_finalize(state: InterviewState) -> bool:
    if state.get("stop_requested"):
        return True
    current_index = int(state.get("current_topic_index") or 0)
    if current_index < 10:
        return False
    report = state.get("last_observer_report")
    if report is None:
        return False
    return report.recommended_next_action in {NextAction.WRAP_UP, NextAction.CHANGE_TOPIC}


def _run_intake(_: InterviewState) -> dict[str, Any]:
    return {}


def _wait_for_user_input(_: InterviewState) -> dict[str, Any]:
    return {}


_EXPERT_NODES: dict[ExpertRole, str] = {
    ExpertRole.TECH_LEAD: "expert_tech_lead",
    ExpertRole.TEAM_LEAD: "expert_team_lead",
    ExpertRole.QA: "expert_qa",
    ExpertRole.DESIGNER: "expert_designer",
    ExpertRole.ANALYST: "expert_analyst",
}


def build_graph() -> Any:
    """Build and compile the interview StateGraph."""

    graph_builder = StateGraph(state_schema=InterviewState)

    graph_builder.add_node("intake", _run_intake)
    graph_builder.add_node("planner", run_planner)
    graph_builder.add_node("observer", run_observer)
    graph_builder.add_node("difficulty", run_difficulty)
    graph_builder.add_node("experts_router", _run_intake)
    graph_builder.add_node("expert_tech_lead", create_expert_node(ExpertRole.TECH_LEAD))
    graph_builder.add_node("expert_team_lead", create_expert_node(ExpertRole.TEAM_LEAD))
    graph_builder.add_node("expert_qa", create_expert_node(ExpertRole.QA))
    graph_builder.add_node("expert_designer", create_expert_node(ExpertRole.DESIGNER))
    graph_builder.add_node("expert_analyst", create_expert_node(ExpertRole.ANALYST))
    graph_builder.add_node("interviewer", run_interviewer)
    graph_builder.add_node("wait_for_user_input", _wait_for_user_input)
    graph_builder.add_node("final_report", run_report)

    graph_builder.set_entry_point("intake")

    graph_builder.add_edge("intake", "planner")
    graph_builder.add_edge("planner", "observer")

    graph_builder.add_conditional_edges(
        "observer",
        _route_after_observer,
        {
            "final_report": "final_report",
            "experts_router": "experts_router",
            "difficulty": "difficulty",
        },
    )

    graph_builder.add_conditional_edges(
        "experts_router",
        _route_experts,
        {
            "difficulty": "difficulty",
            "expert_tech_lead": "expert_tech_lead",
            "expert_team_lead": "expert_team_lead",
            "expert_qa": "expert_qa",
            "expert_designer": "expert_designer",
            "expert_analyst": "expert_analyst",
        },
    )

    for node in _EXPERT_NODES.values():
        graph_builder.add_edge(node, "experts_router")

    graph_builder.add_edge("difficulty", "interviewer")
    graph_builder.add_edge("interviewer", "wait_for_user_input")
    graph_builder.add_edge("wait_for_user_input", END)
    graph_builder.add_edge("final_report", END)

    return graph_builder.compile()
