"""Scenario runner for scripted interview simulations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.interview_coach.graph import build_graph
from src.interview_coach.logger import InterviewLogger
from src.interview_coach.models import InterviewIntake, TurnLog
from src.interview_coach.skills import build_skill_baseline


def _load_scenario(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_turn_log(state: dict[str, Any]) -> TurnLog | None:
    turn_log = state.get("turn_log")
    if isinstance(turn_log, TurnLog):
        return turn_log
    turns = state.get("turns") or []
    if turns:
        last = turns[-1]
        if isinstance(last, TurnLog):
            return last
    return None


def _update_observer_reports(state: dict[str, Any]) -> None:
    report = state.get("last_observer_report")
    if report is None:
        return
    reports = state.get("observer_reports")
    if reports is None:
        state["observer_reports"] = [report]
        return
    if report not in reports:
        reports.append(report)


def _assert_internal_thoughts(turns: list[TurnLog]) -> None:
    hallucination_ok = any("hallucination=True" in turn.internal_thoughts for turn in turns)
    role_reversal_ok = any("role_reversal=True" in turn.internal_thoughts for turn in turns)
    if not hallucination_ok or not role_reversal_ok:
        missing = []
        if not hallucination_ok:
            missing.append("hallucination")
        if not role_reversal_ok:
            missing.append("role_reversal")
        raise AssertionError("internal_thoughts missing expected flags: " + ", ".join(missing))


def run_scenario(path: str) -> str:
    scenario = _load_scenario(path)
    intake = InterviewIntake(**scenario["intake"])
    scripted_messages = scenario.get("scripted_user_messages") or []

    logger = InterviewLogger()
    logger.start_session(intake)

    state: dict[str, Any] = {
        "intake": intake,
        "difficulty": "MEDIUM",
        "difficulty_reason": "",
        "topics_covered": [],
        "asked_questions": [],
        "turns": [],
        "observer_reports": [],
        "skill_matrix": build_skill_baseline(),
        "stop_requested": False,
        "expert_evaluations_current_turn": {},
    }

    graph = build_graph()
    state = graph.invoke(state)
    _update_observer_reports(state)
    turn_log = _extract_turn_log(state)
    if turn_log:
        logger.append_turn(turn_log)

    for message in scripted_messages:
        state["last_user_message"] = message
        state["expert_evaluations_current_turn"] = {}
        if str(message).strip().lower() in {"stop", "стоп", "стоп интервью"}:
            state["stop_requested"] = True

        state = graph.invoke(state)
        _update_observer_reports(state)

        turn_log = _extract_turn_log(state)
        if turn_log:
            logger.append_turn(turn_log)

        if state.get("final_feedback") is not None:
            break

    _assert_internal_thoughts(logger.turns)

    run_path = f"runs/interview_log_{Path(path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    logger.set_final_feedback(state.get("final_feedback_text") or state.get("final_feedback"))
    logger.save(run_path)
    return run_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, help="Path to scenario JSON")
    args = parser.parse_args()

    output_path = run_scenario(args.scenario)
    print(f"Scenario log saved to {output_path}")
