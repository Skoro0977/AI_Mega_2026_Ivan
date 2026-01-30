from __future__ import annotations

import json
from pathlib import Path

from src.interview_coach.models import FinalFeedback, NextAction, ObserverFlags, ObserverReport
from src.interview_coach.scenarios import run_scenario


class _FakeObserverAgent:
    def invoke(self, messages):
        last_user = ""
        for message in reversed(messages):
            if getattr(message, "type", "") == "human":
                last_user = str(message.content)
                break

        flags = ObserverFlags()
        if "kafka" in last_user.lower():
            flags.hallucination = True
        if "ask you" in last_user.lower():
            flags.role_reversal = True

        report = ObserverReport(
            detected_topic="system design",
            answer_quality=3.5,
            confidence=0.7,
            flags=flags,
            recommended_next_action=NextAction.ASK_DEEPER,
            recommended_question_style="Ask for details",
            fact_check_notes="",
            skills_delta={"system design": 0.2},
        )
        return {"structured_response": report}


class _FakeInterviewerRunnable:
    def __init__(self) -> None:
        self._counter = 0

    def invoke(self, _payload):
        self._counter += 1
        return f"Question {self._counter}?"


class _FakeReportAgent:
    def invoke(self, _messages):
        feedback = FinalFeedback.model_validate(
            {
                "decision": {
                    "grade": "junior",
                    "recommendation": "Proceed",
                    "confidence_score": 0.6,
                },
                "hard_skills": {
                    "confirmed": ["SQL"],
                    "gaps_with_correct_answers": {},
                },
                "soft_skills": {
                    "clarity": "Clear",
                    "honesty": "Honest",
                    "engagement": "Engaged",
                    "examples": [],
                },
                "roadmap": {
                    "next_steps": ["Practice system design"],
                    "links": [],
                },
            }
        )
        return {"structured_response": feedback}


def test_scenario_smoke(tmp_path, monkeypatch):
    from src.interview_coach.nodes import interviewer as interviewer_node
    from src.interview_coach.nodes import observer as observer_node
    from src.interview_coach.nodes import report as report_node

    monkeypatch.setattr(observer_node, "get_observer_agent", lambda *_args, **_kw: _FakeObserverAgent())
    monkeypatch.setattr(
        interviewer_node,
        "get_interviewer_runnable",
        lambda *_args, **_kw: _FakeInterviewerRunnable(),
    )
    monkeypatch.setattr(report_node, "get_report_agent", lambda *_args, **_kw: _FakeReportAgent())

    scenario = {
        "intake": {
            "participant_name": "Test",
            "position": "Backend Engineer",
            "grade_target": "middle",
            "experience_summary": "Python dev",
        },
        "scripted_user_messages": [
            "Kafka guarantees exactly-once delivery by default.",
            "Can I ask you about the team?",
            "stop",
        ],
    }

    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    output_path = run_scenario(str(scenario_path))
    assert Path(output_path).exists()
