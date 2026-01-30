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
        self.final_feedback: str | dict[str, Any] | None = None

    def start_session(self, intake: InterviewIntake) -> None:
        self.intake = intake

    def append_turn(self, turn: TurnLog) -> None:
        self.turns.append(turn)

    def set_final_feedback(self, feedback: str | dict[str, Any] | BaseModel) -> None:
        if isinstance(feedback, BaseModel):
            self.final_feedback = feedback.model_dump()
        else:
            self.final_feedback = feedback

    def save(self, path: str) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "participant_name": self.intake.participant_name if self.intake else "",
            "turns": [turn.model_dump() for turn in self.turns],
            "final_feedback": self.final_feedback if self.final_feedback is not None else "",
        }

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
