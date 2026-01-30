from __future__ import annotations

import pytest

from src.interview_coach.logger import validate_schema


def test_validate_schema_accepts_valid_payload():
    payload = {
        "participant_name": "Jane",
        "turns": [
            {
                "turn_id": 1,
                "agent_visible_message": "Question?",
                "user_message": "Answer.",
                "internal_thoughts": "[Observer]: ok. [Interviewer]: ask.",
            }
        ],
        "final_feedback": "Summary text.",
    }

    validate_schema(payload)


def test_validate_schema_rejects_extra_turn_keys():
    payload = {
        "participant_name": "Jane",
        "turns": [
            {
                "turn_id": 1,
                "agent_visible_message": "Question?",
                "user_message": "Answer.",
                "internal_thoughts": "[Observer]: ok. [Interviewer]: ask.",
                "topic": "databases",
            }
        ],
        "final_feedback": "Summary text.",
    }

    with pytest.raises(ValueError, match="turn keys"):
        validate_schema(payload)
