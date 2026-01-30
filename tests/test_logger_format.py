from __future__ import annotations

import json

from src.interview_coach.logger import InterviewLogger
from src.interview_coach.models import (
    GradeTarget,
    InterviewIntake,
    ObserverFlags,
    TurnLog,
)


def test_logger_format(tmp_path):
    logger = InterviewLogger()
    intake = InterviewIntake(
        participant_name="Jane",
        position="Backend Engineer",
        grade_target=GradeTarget.MIDDLE,
        experience_summary="5 years with Python",
    )
    logger.start_session(intake)

    turn = TurnLog(
        turn_id=1,
        agent_visible_message="Question 1?",
        user_message="Answer 1",
        internal_thoughts="[Observer]: ok. [Interviewer]: strategy=ask.",
        topic="databases",
        difficulty_before=3,
        difficulty_after=3,
        flags=ObserverFlags(off_topic=False),
        skills_delta={"sql": 0.5},
    )
    logger.append_turn(turn)
    logger.set_final_feedback({"status": "done"})

    output_path = tmp_path / "interview_log.json"
    logger.save(str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["participant_name"] == "Jane"
    assert isinstance(payload["turns"], list)
    assert payload["turns"][0]["turn_id"] == 1
    assert payload["turns"][0]["agent_visible_message"] == "Question 1?"
    assert payload["turns"][0]["user_message"] == "Answer 1"
    assert "[Observer]:" in payload["turns"][0]["internal_thoughts"]
    assert "[Interviewer]:" in payload["turns"][0]["internal_thoughts"]
    assert payload["final_feedback"] == {"status": "done"}
