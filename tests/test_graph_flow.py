from __future__ import annotations

from src.interview_coach.graph import build_graph
from src.interview_coach.skills import build_skill_baseline


class _FakeInterviewerRunnable:
    def invoke(self, _payload):
        return "First question?"


def test_initial_invoke_skips_observer_and_turn_log(monkeypatch):
    from src.interview_coach.nodes import interviewer as interviewer_node

    monkeypatch.setattr(
        interviewer_node,
        "get_interviewer_runnable",
        lambda *_args, **_kwargs: _FakeInterviewerRunnable(),
    )

    state = {
        "difficulty": 3,
        "topics_covered": [],
        "asked_questions": [],
        "turns": [],
        "observer_reports": [],
        "skill_matrix": build_skill_baseline(),
        "stop_requested": False,
        "pending_interviewer_message": None,
        "pending_internal_thoughts": None,
        "pending_report": None,
        "pending_difficulty": None,
    }

    graph = build_graph()
    state = graph.invoke(state)

    assert state.get("last_interviewer_message") == "First question?"
    assert state.get("turn_log") is None
    assert state.get("turns") == []
