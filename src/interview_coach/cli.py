"""CLI runner for the Multi-Agent Interview Coach."""

from __future__ import annotations

from datetime import datetime
import logging
import select
import sys
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
from src.interview_coach.skills import build_skill_baseline

STOP_COMMANDS = {"stop", "стоп", "стоп интервью"}


def _sanitize_input(value: str) -> str:
    # Strip control chars to avoid terminal artifacts and hidden separators.
    cleaned = "".join(ch for ch in value if ch.isprintable())
    return cleaned.strip()


def _prompt(text: str) -> str:
    print(text, end="", flush=True)
    raw_bytes = sys.stdin.buffer.readline()
    if not raw_bytes:
        logging.info("CLI: input EOF")
        raise EOFError
    lines = [raw_bytes]
    extra_lines = 0
    # Capture pasted multi-line input without requiring an extra blank line.
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            break
        more = sys.stdin.buffer.readline()
        if not more:
            break
        lines.append(more)
        extra_lines += 1
        if extra_lines >= 200:
            logging.info("CLI: input truncated (too many lines)")
            break
    decoded_lines = [line.decode("utf-8", errors="ignore") for line in lines]
    cleaned_lines = [_sanitize_input(line).rstrip() for line in decoded_lines]
    cleaned = "\n".join(cleaned_lines).strip()
    if cleaned != "".join(decoded_lines):
        logging.info("CLI: stripped non-printable characters from input")
    if extra_lines:
        logging.info("CLI: input received (lines=%d, len=%d)", extra_lines + 1, len(cleaned))
    else:
        logging.info("CLI: input received (len=%d)", len(cleaned))
    return cleaned


def _prompt_multiline(text: str) -> str:
    print(text, end="", flush=True)
    lines: list[str] = []
    while True:
        raw_bytes = sys.stdin.buffer.readline()
        if not raw_bytes:
            logging.info("CLI: multiline input EOF")
            break
        line = raw_bytes.decode("utf-8", errors="ignore")
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


def _invoke_graph(
    state: dict[str, Any],
    graph: Any,
    logger: InterviewLogger,
    run_path: str,
    last_logged_turn_id: int,
) -> tuple[dict[str, Any], int]:
    state = graph.invoke(state)
    _update_observer_reports(state)
    turn_log = _extract_turn_log(state)
    if turn_log and turn_log.turn_id > last_logged_turn_id:
        logger.append_turn(turn_log)
        last_logged_turn_id = turn_log.turn_id
        logger.save(run_path)
    return state, last_logged_turn_id


def _fallback_feedback(reason: str) -> str:
    return f"Интервью завершено без финального отчёта. Причина: {reason}."


def _resolve_final_feedback(state: dict[str, Any], reason: str) -> str:
    final_text = state.get("final_feedback_text")
    if isinstance(final_text, str) and final_text.strip():
        return final_text.strip()
    final_feedback = state.get("final_feedback")
    if isinstance(final_feedback, str) and final_feedback.strip():
        return final_feedback.strip()
    if final_feedback is not None:
        return str(final_feedback)
    return _fallback_feedback(reason)


def _finalize_and_save(
    state: dict[str, Any],
    logger: InterviewLogger,
    run_path: str,
    reason: str,
) -> None:
    final_text = _resolve_final_feedback(state, reason)
    logger.set_final_feedback(final_text)
    logger.save(run_path)
    print("\nФинальный отчёт:\n" + final_text)


def run_cli(max_turns: int = 30, run_path: str | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    if max_turns < 1:
        raise ValueError("max_turns must be >= 1")
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
        "skill_matrix": build_skill_baseline(),
        "stop_requested": False,
        "pending_interviewer_message": None,
        "pending_internal_thoughts": None,
        "pending_report": None,
        "pending_difficulty": None,
    }

    graph = build_graph()
    resolved_run_path = run_path or (
        f"runs/interview_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    last_printed_message = ""
    last_logged_turn_id = 0
    stop_reason: str | None = None

    print("\nГенерация ответа...", flush=True)
    logging.info("CLI: invoking graph (initial)")
    state, last_logged_turn_id = _invoke_graph(
        state,
        graph,
        logger,
        resolved_run_path,
        last_logged_turn_id,
    )
    last_message = state.get("last_interviewer_message") or ""
    if last_message and last_message != last_printed_message:
        print(f"\nИнтервьюер: {last_message}")
        last_printed_message = last_message
    if last_logged_turn_id >= max_turns:
        print(f"\nДостигнут лимит ходов ({max_turns}). Интервью завершается.")
        state["stop_requested"] = True
        stop_reason = f"достигнут лимит ходов (max_turns={max_turns})"
        try:
            state, last_logged_turn_id = _invoke_graph(
                state,
                graph,
                logger,
                resolved_run_path,
                last_logged_turn_id,
            )
        except Exception:
            logging.exception("CLI: failed to finalize after max_turns")
        _finalize_and_save(state, logger, resolved_run_path, stop_reason)
        return

    while True:
        print("\nОжидание ответа кандидата...", flush=True)
        try:
            user_message = _prompt("\nКандидат: ")
            if _should_stop(user_message):
                state["stop_requested"] = True
                stop_reason = "команда stop"
            state["last_user_message"] = user_message
        except EOFError:
            print("\nEOF: интервью завершается.", flush=True)
            state["stop_requested"] = True
            state["last_user_message"] = ""
            stop_reason = "EOF"
            try:
                state, last_logged_turn_id = _invoke_graph(
                    state,
                    graph,
                    logger,
                    resolved_run_path,
                    last_logged_turn_id,
                )
            except Exception:
                logging.exception("CLI: failed to finalize after EOF")
            _finalize_and_save(state, logger, resolved_run_path, stop_reason)
            break
        except KeyboardInterrupt:
            print("\nInterrupted: интервью завершается.", flush=True)
            state["stop_requested"] = True
            state["last_user_message"] = ""
            stop_reason = "KeyboardInterrupt"
            try:
                state, last_logged_turn_id = _invoke_graph(
                    state,
                    graph,
                    logger,
                    resolved_run_path,
                    last_logged_turn_id,
                )
            except Exception:
                logging.exception("CLI: failed to finalize after KeyboardInterrupt")
            _finalize_and_save(state, logger, resolved_run_path, stop_reason)
            break

        print("\nГенерация ответа...", flush=True)
        logging.info("CLI: invoking graph (turn)")
        state, last_logged_turn_id = _invoke_graph(
            state,
            graph,
            logger,
            resolved_run_path,
            last_logged_turn_id,
        )

        last_message = state.get("last_interviewer_message") or ""
        if last_message and last_message != last_printed_message:
            print(f"\nИнтервьюер: {last_message}")
            last_printed_message = last_message

        final_feedback = state.get("final_feedback")
        final_feedback_text = state.get("final_feedback_text")
        if final_feedback is not None:
            _finalize_and_save(
                state,
                logger,
                resolved_run_path,
                stop_reason or "запрошен финальный отчёт",
            )
            break
        if last_logged_turn_id >= max_turns:
            print(f"\nДостигнут лимит ходов ({max_turns}). Интервью завершается.")
            state["stop_requested"] = True
            stop_reason = f"достигнут лимит ходов (max_turns={max_turns})"
            try:
                state, last_logged_turn_id = _invoke_graph(
                    state,
                    graph,
                    logger,
                    resolved_run_path,
                    last_logged_turn_id,
                )
            except Exception:
                logging.exception("CLI: failed to finalize after max_turns")
            _finalize_and_save(state, logger, resolved_run_path, stop_reason)
            break

        logger.save(resolved_run_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-turns", type=int, default=12, help="Max interview turns")
    args = parser.parse_args()

    run_cli(max_turns=args.max_turns)
