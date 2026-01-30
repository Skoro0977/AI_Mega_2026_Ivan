"""Skill vocabulary and baseline scores for the interview coach."""

from __future__ import annotations

SKILL_KEYS: tuple[str, ...] = (
    "python_basics",
    "async",
    "db_modeling",
    "queues",
    "observability",
    "architecture",
    "testing",
    "rag_langchain",
)


def build_skill_baseline() -> dict[str, float]:
    """Return a zeroed skill baseline for state initialization."""
    return {key: 0.0 for key in SKILL_KEYS}
