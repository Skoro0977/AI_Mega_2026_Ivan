"""Pydantic models for the Multi-Agent Interview Coach domain."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class GradeTarget(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"


class NextAction(str, Enum):
    ASK_DEEPER = "ASK_DEEPER"
    ASK_EASIER = "ASK_EASIER"
    CHANGE_TOPIC = "CHANGE_TOPIC"
    HANDLE_OFFTOPIC = "HANDLE_OFFTOPIC"
    HANDLE_HALLUCINATION = "HANDLE_HALLUCINATION"
    HANDLE_ROLE_REVERSAL = "HANDLE_ROLE_REVERSAL"
    WRAP_UP = "WRAP_UP"


class InterviewIntake(BaseModel):
    """Initial interview intake provided by the participant or orchestrator."""

    participant_name: str
    position: str
    grade_target: GradeTarget
    experience_summary: str


class ObserverFlags(BaseModel):
    off_topic: bool = False
    hallucination: bool = False
    contradiction: bool = False
    role_reversal: bool = False


class TurnLog(BaseModel):
    """One logged interaction turn with visible output and internal reasoning."""

    turn_id: int
    agent_visible_message: str
    user_message: str
    internal_thoughts: str
    topic: Optional[str] = None
    difficulty_before: Optional[int] = None
    difficulty_after: Optional[int] = None
    flags: Optional[ObserverFlags] = None
    skills_delta: Optional[dict[str, float]] = None

    @field_validator("difficulty_before", "difficulty_after")
    @classmethod
    def validate_difficulty(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if not 1 <= value <= 5:
            raise ValueError("difficulty must be within 1..5")
        return value


class SkillEvidence(BaseModel):
    """Evidence unit for a specific skill topic assessment."""

    topic: str
    claim: str
    is_correct: float = Field(..., ge=0.0, le=1.0)
    notes: str
    turn_id: int


class SkillTopicState(BaseModel):
    """Aggregated state for a given skill topic with evidence and gaps."""

    level_estimate: int
    confirmed: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    evidence: list[SkillEvidence] = Field(default_factory=list)

    @field_validator("level_estimate")
    @classmethod
    def validate_level(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError("level_estimate must be within 1..5")
        return value


class SkillMatrix(BaseModel):
    """Wrapper for per-topic skill states keyed by topic name."""

    topics: dict[str, SkillTopicState] = Field(default_factory=dict)


class ObserverReport(BaseModel):
    """Observer assessment produced for each turn and used for hidden reflection."""

    detected_topic: str
    answer_quality: float = Field(..., ge=0.0, le=5.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    flags: ObserverFlags
    recommended_next_action: NextAction
    recommended_question_style: str
    fact_check_notes: Optional[str] = None
    skills_delta: Optional[dict[str, float]] = None


class Decision(BaseModel):
    grade: GradeTarget
    recommendation: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class HardSkillsFeedback(BaseModel):
    confirmed: list[str] = Field(default_factory=list)
    gaps_with_correct_answers: dict[str, str] = Field(default_factory=dict)


class SoftSkillsFeedback(BaseModel):
    clarity: str
    honesty: str
    engagement: str
    examples: list[str] = Field(default_factory=list)


class Roadmap(BaseModel):
    next_steps: list[str] = Field(default_factory=list)
    links: Optional[list[str]] = None


class FinalFeedback(BaseModel):
    """Final feedback summary after the interview stops."""

    decision: Decision
    hard_skills: HardSkillsFeedback
    soft_skills: SoftSkillsFeedback
    roadmap: Roadmap
