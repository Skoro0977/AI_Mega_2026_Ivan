"""Interview logging utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.interview_coach.models import InterviewIntake, TurnLog


class InterviewLogger:
    """Collects interview turns and writes them to a JSON log file."""

    def __init__(self) -> None:
        self.intake: InterviewIntake | None = None
        self.turns: list[TurnLog] = []
        self.final_feedback: str | None = None

    def start_session(self, intake: InterviewIntake) -> None:
        self.intake = intake

    def append_turn(self, turn: TurnLog) -> None:
        self.turns.append(turn)

    def set_final_feedback(self, feedback: str | dict[str, Any] | BaseModel) -> None:
        self.final_feedback = _coerce_feedback_text(feedback)

    def save(self, path: str) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "participant_name": self.intake.participant_name if self.intake else "",
            "turns": [_serialize_turn(turn) for turn in self.turns],
            "final_feedback": self.final_feedback or "",
        }
        validate_schema(payload)

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)


def _serialize_turn(turn: TurnLog) -> dict[str, Any]:
    return {
        "turn_id": turn.turn_id,
        "agent_visible_message": turn.agent_visible_message,
        "user_message": turn.user_message,
        "internal_thoughts": turn.internal_thoughts,
    }


def _coerce_feedback_text(feedback: str | dict[str, Any] | BaseModel) -> str:
    if isinstance(feedback, BaseModel):
        return json.dumps(feedback.model_dump(), ensure_ascii=False, indent=2)
    if isinstance(feedback, dict):
        return json.dumps(feedback, ensure_ascii=False, indent=2)
    if isinstance(feedback, str):
        return feedback
    return str(feedback)


def validate_schema(log_dict: dict[str, Any]) -> None:
    expected_top = {"participant_name", "turns", "final_feedback"}
    actual_top = set(log_dict.keys())
    missing_top = expected_top - actual_top
    extra_top = actual_top - expected_top
    if missing_top or extra_top:
        raise ValueError(
            f"Invalid log schema (top-level keys). Missing: {sorted(missing_top)}; Extra: {sorted(extra_top)}"
        )
    if not isinstance(log_dict["participant_name"], str):
        raise ValueError("Invalid log schema: participant_name must be a string.")
    if not isinstance(log_dict["final_feedback"], str):
        raise ValueError("Invalid log schema: final_feedback must be a string.")
    turns = log_dict["turns"]
    if not isinstance(turns, list):
        raise ValueError("Invalid log schema: turns must be a list.")

    expected_turn = {"turn_id", "agent_visible_message", "user_message", "internal_thoughts"}
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError(f"Invalid log schema: turn {index} must be an object.")
        actual_turn = set(turn.keys())
        missing_turn = expected_turn - actual_turn
        extra_turn = actual_turn - expected_turn
        if missing_turn or extra_turn:
            raise ValueError(
                "Invalid log schema (turn keys). "
                f"Turn {index} missing: {sorted(missing_turn)}; "
                f"extra: {sorted(extra_turn)}"
            )
        if not isinstance(turn["turn_id"], int):
            raise ValueError(f"Invalid log schema: turn {index} turn_id must be int.")
        if not isinstance(turn["agent_visible_message"], str):
            raise ValueError(f"Invalid log schema: turn {index} agent_visible_message must be str.")
        if not isinstance(turn["user_message"], str):
            raise ValueError(f"Invalid log schema: turn {index} user_message must be str.")
        if not isinstance(turn["internal_thoughts"], str):
            raise ValueError(f"Invalid log schema: turn {index} internal_thoughts must be str.")
