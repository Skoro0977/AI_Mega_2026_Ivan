"""CLI runner for the Multi-Agent Interview Coach."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interview_coach.graph import build_graph
from src.interview_coach.logger import InterviewLogger
from src.interview_coach.models import GradeTarget, InterviewIntake, TurnLog

STOP_COMMANDS = {"stop", "стоп", "стоп интервью"}


def _prompt(text: str) -> str:
    return input(text).strip()


def _prompt_multiline(text: str) -> str:
    print(text, end="")
    lines: list[str] = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _collect_intake() -> InterviewIntake:
    name = _prompt("Имя кандидата: ")
    position = _prompt("Вакансия/роль: ")
    grade_raw = _prompt("Уровень (intern/junior/middle/senior/staff/principal): ")
    experience = _prompt_multiline(
        "Кратко об опыте (можно в несколько строк; пустая строка завершает ввод): "
    )
    grade = GradeTarget(grade_raw.strip().lower())
    return InterviewIntake(
        participant_name=name,
        position=position,
        grade_target=grade,
        experience_summary=experience,
    )


def _should_stop(message: str) -> bool:
    return message.strip().lower() in STOP_COMMANDS


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


def run_cli() -> None:
    intake = _collect_intake()
    logger = InterviewLogger()
    logger.start_session(intake)

    state: dict[str, Any] = {
        "intake": intake,
        "difficulty": 3,
        "topics_covered": [],
        "asked_questions": [],
        "turns": [],
        "observer_reports": [],
        "stop_requested": False,
    }

    graph = build_graph()
    run_path = f"runs/interview_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    state = graph.invoke(state)
    _update_observer_reports(state)
    turn_log = _extract_turn_log(state)
    if turn_log:
        logger.append_turn(turn_log)
        print(f"\nИнтервьюер: {turn_log.agent_visible_message}")
        logger.save(run_path)

    while True:
        user_message = _prompt("\nКандидат: ")
        if _should_stop(user_message):
            state["stop_requested"] = True
        state["last_user_message"] = user_message

        state = graph.invoke(state)
        _update_observer_reports(state)

        turn_log = _extract_turn_log(state)
        if turn_log:
            logger.append_turn(turn_log)
            print(f"\nИнтервьюер: {turn_log.agent_visible_message}")

        final_feedback = state.get("final_feedback")
        final_feedback_text = state.get("final_feedback_text")
        if final_feedback is not None:
            logger.set_final_feedback(final_feedback)
            logger.save(run_path)
            if final_feedback_text:
                print("\nФинальный отчёт:\n" + final_feedback_text)
            else:
                print("\nФинальный отчёт:")
                print(final_feedback)
            break

        logger.save(run_path)


if __name__ == "__main__":
    run_cli()
