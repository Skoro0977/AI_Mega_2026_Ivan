from __future__ import annotations

from src.interview_coach.models import FinalFeedback, ObserverReport


def test_observer_report_validation():
    payload = {
        "detected_topic": "system design",
        "answer_quality": 4.5,
        "confidence": 0.7,
        "flags": {
            "off_topic": False,
            "hallucination": False,
            "contradiction": False,
            "role_reversal": False,
        },
        "recommended_next_action": "ASK_DEEPER",
        "recommended_question_style": "Ask for trade-offs",
        "fact_check_notes": "",
        "skills_delta": {"distributed systems": 0.5},
    }

    report = ObserverReport.model_validate(payload)
    assert report.detected_topic == "system design"
    assert report.answer_quality == 4.5


def test_final_feedback_validation():
    payload = {
        "decision": {
            "grade": "junior",
            "recommendation": "Proceed with technical deep dive.",
            "confidence_score": 0.6,
        },
        "hard_skills": {
            "confirmed": ["SQL", "Caching"],
            "gaps_with_correct_answers": {"Concurrency": "Use locks or queues."},
        },
        "soft_skills": {
            "clarity": "Clear and structured",
            "honesty": "Admitted uncertainty",
            "engagement": "Asked clarifying questions",
            "examples": ["Shared a scaling story"],
        },
        "roadmap": {
            "next_steps": ["Review distributed systems basics"],
            "links": [],
        },
    }

    feedback = FinalFeedback.model_validate(payload)
    assert feedback.decision.grade.value == "junior"
    assert feedback.roadmap.next_steps
