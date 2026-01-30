"""Pydantic models for the Multi-Agent Interview Coach domain."""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _clamp(value: object, low: float, high: float) -> float:
    numeric = _coerce_float(value, low)
    if numeric < low:
        return low
    if numeric > high:
        return high
    return numeric


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


class ExpertRole(str, Enum):
    TECH_LEAD = "tech_lead"
    TEAM_LEAD = "team_lead"
    QA = "qa"
    DESIGNER = "designer"
    ANALYST = "analyst"


class InterviewIntake(BaseModel):
    """Initial interview intake provided by the participant or orchestrator."""

    participant_name: str
    position: str
    grade_target: GradeTarget
    experience_summary: str


class PlannedTopics(BaseModel):
    """Planner output with ordered interview topics."""

    topics: list[str] = Field(default_factory=list)

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                raise ValueError("topics must be non-empty strings")
            cleaned.append(text)
        if len(cleaned) != 10:
            raise ValueError("topics must contain exactly 10 items")
        return cleaned


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
    topic: str | None = None
    difficulty_before: int | None = None
    difficulty_after: int | None = None
    flags: ObserverFlags | None = None
    skills_delta: dict[str, float] | None = None

    @field_validator("difficulty_before", "difficulty_after")
    @classmethod
    def validate_difficulty(cls, value: int | None) -> int | None:
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
    fact_check_notes: str | None = None
    skills_delta: dict[str, float] | None = None

    @field_validator("answer_quality", mode="before")
    @classmethod
    def clamp_answer_quality(cls, value: object) -> float:
        return _clamp(value, 0.0, 5.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: object) -> float:
        return _clamp(value, 0.0, 1.0)

    @field_validator("skills_delta", mode="before")
    @classmethod
    def coerce_skills_delta(cls, value: object) -> dict[str, float] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            return None
        cleaned: dict[str, float] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                continue
            try:
                numeric = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            cleaned[key] = numeric
        return cleaned or None


class Decision(BaseModel):
    grade: GradeTarget
    recommendation: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class HardSkillsFeedback(BaseModel):
    confirmed: list[str] = Field(default_factory=list)
    gaps_with_correct_answers: dict[str, str] = Field(default_factory=dict)

    @field_validator("gaps_with_correct_answers", mode="before")
    @classmethod
    def coerce_gaps(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            return {}
        cleaned: dict[str, str] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                continue
            if isinstance(raw, list):
                text = " ".join(str(item) for item in raw if item is not None).strip()
            else:
                text = str(raw).strip()
            if text:
                cleaned[key] = text
        return cleaned


class SoftSkillsFeedback(BaseModel):
    clarity: str
    honesty: str
    engagement: str
    examples: list[str] = Field(default_factory=list)


class Roadmap(BaseModel):
    next_steps: list[str] = Field(default_factory=list)
    links: list[str] | None = None


class FinalFeedback(BaseModel):
    """Final feedback summary after the interview stops."""

    decision: Decision
    hard_skills: HardSkillsFeedback
    soft_skills: SoftSkillsFeedback
    roadmap: Roadmap
