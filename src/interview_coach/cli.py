"""CLI runner for the Multi-Agent Interview Coach."""

from __future__ import annotations

from datetime import datetime
import logging
import warnings
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

from src.interview_coach.graph import build_graph
from src.interview_coach.logger import InterviewLogger
from src.interview_coach.models import GradeTarget, InterviewIntake, TurnLog

STOP_COMMANDS = {"stop", "стоп", "стоп интервью"}


def _sanitize_input(value: str) -> str:
    # Strip control chars to avoid terminal artifacts and hidden separators.
    cleaned = "".join(ch for ch in value if ch.isprintable())
    return cleaned.strip()


def _prompt(text: str) -> str:
    raw = input(text)
    cleaned = _sanitize_input(raw)
    if cleaned != raw:
        logging.info("CLI: stripped non-printable characters from input")
    logging.info("CLI: input received (len=%d)", len(cleaned))
    return cleaned


def _prompt_multiline(text: str) -> str:
    print(text, end="")
    lines: list[str] = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(_sanitize_input(line).rstrip())
    combined = "\n".join(lines).strip()
    logging.info("CLI: multiline input received (len=%d)", len(combined))
    return combined


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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
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
        "pending_interviewer_message": None,
        "pending_internal_thoughts": None,
        "pending_report": None,
        "pending_difficulty": None,
    }

    graph = build_graph()
    run_path = f"runs/interview_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    last_printed_message = ""
    last_logged_turn_id = 0

    print("\nГенерация ответа...", flush=True)
    logging.info("CLI: invoking graph (initial)")
    state = graph.invoke(state)
    _update_observer_reports(state)
    turn_log = _extract_turn_log(state)
    if turn_log and turn_log.turn_id > last_logged_turn_id:
        logger.append_turn(turn_log)
        last_logged_turn_id = turn_log.turn_id
        logger.save(run_path)
    last_message = state.get("last_interviewer_message") or ""
    if last_message and last_message != last_printed_message:
        print(f"\nИнтервьюер: {last_message}")
        last_printed_message = last_message

    while True:
        print("\nОжидание ответа кандидата...", flush=True)
        user_message = _prompt("\nКандидат: ")
        if _should_stop(user_message):
            state["stop_requested"] = True
        state["last_user_message"] = user_message

        print("\nГенерация ответа...", flush=True)
        logging.info("CLI: invoking graph (turn)")
        state = graph.invoke(state)
        _update_observer_reports(state)

        turn_log = _extract_turn_log(state)
        if turn_log and turn_log.turn_id > last_logged_turn_id:
            logger.append_turn(turn_log)
            last_logged_turn_id = turn_log.turn_id

        last_message = state.get("last_interviewer_message") or ""
        if last_message and last_message != last_printed_message:
            print(f"\nИнтервьюер: {last_message}")
            last_printed_message = last_message

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
