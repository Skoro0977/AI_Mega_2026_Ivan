from __future__ import annotations

import json
from pathlib import Path

from src.interview_coach.cli import run_cli
from src.interview_coach.models import GradeTarget, InterviewIntake, TurnLog


class DummyGraph:
    def __init__(self) -> None:
        self.counter = 0

    def invoke(self, state: dict) -> dict:
        if state.get("stop_requested"):
            return {**state, "final_feedback_text": "Final report."}
        self.counter += 1
        turn = TurnLog(
            turn_id=self.counter,
            agent_visible_message=f"Q{self.counter}?",
            user_message=state.get("last_user_message") or "",
            internal_thoughts="[Observer]: ok. [Interviewer]: ask.",
        )
        return {**state, "turn_log": turn, "last_interviewer_message": f"Q{self.counter}?"}


def _intake() -> InterviewIntake:
    return InterviewIntake(
        participant_name="Jane",
        position="Backend Engineer",
        grade_target=GradeTarget.MIDDLE,
        experience_summary="5 years with Python",
    )


def _load_log(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_finalizes_on_eof(monkeypatch, tmp_path):
    log_path = tmp_path / "log.json"
    monkeypatch.setattr("src.interview_coach.cli.build_graph", lambda: DummyGraph())
    monkeypatch.setattr("src.interview_coach.cli._collect_intake", _intake)

    def _raise_eof(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("src.interview_coach.cli._prompt", _raise_eof)
    run_cli(max_turns=5, run_path=str(log_path))

    payload = _load_log(log_path)
    assert payload["final_feedback"] == "Final report."


def test_cli_finalizes_on_max_turns(monkeypatch, tmp_path):
    log_path = tmp_path / "log.json"
    monkeypatch.setattr("src.interview_coach.cli.build_graph", lambda: DummyGraph())
    monkeypatch.setattr("src.interview_coach.cli._collect_intake", _intake)

    answers = iter(["Answer."])

    def _prompt(_: str) -> str:
        return next(answers)

    monkeypatch.setattr("src.interview_coach.cli._prompt", _prompt)
    run_cli(max_turns=2, run_path=str(log_path))

    payload = _load_log(log_path)
    assert payload["final_feedback"] == "Final report."
