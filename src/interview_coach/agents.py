"""LangChain agent builders and message helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.interview_coach.models import FinalFeedback, ObserverOutput, PlannedTopics
from src.interview_coach.prompts import load_prompt
from src.interview_coach.settings import get_settings

_ModelKey = tuple[str, float, int]

_MODEL_CACHE: dict[_ModelKey, ChatOpenAI] = {}
_INTERVIEWER_CACHE: dict[_ModelKey, Any] = {}
_OBSERVER_CACHE: dict[_ModelKey, Any] = {}
_REPORT_CACHE: dict[_ModelKey, Any] = {}
_PLANNER_CACHE: dict[_ModelKey, Any] = {}

_MAX_CONTEXT_STRING_LEN = 800


def build_model(model: str, temperature: float, max_retries: int) -> ChatOpenAI:
    """Create or reuse a ChatOpenAI model instance."""
    key = (model, temperature, max_retries)
    if key not in _MODEL_CACHE:
        settings = get_settings()
        client_kwargs: dict[str, Any] = {}
        if settings.openai_api_key:
            client_kwargs["openai_api_key"] = settings.openai_api_key
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        _MODEL_CACHE[key] = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            **client_kwargs,
        )
    return _MODEL_CACHE[key]


def build_interviewer_input(state: Mapping[str, Any]) -> dict[str, str]:
    """Build the input payload for the interviewer prompt."""
    payload = {
        "intake": _serialize(state.get("intake")),
        "observer_report": _serialize(state.get("observer_report")),
        "skill_matrix": _serialize(state.get("skill_matrix")),
        "recent_turns": _serialize(_tail(state.get("turns"))),
        "last_user_message": state.get("last_user_message") or "",
        "last_interviewer_message": state.get("last_interviewer_message") or "",
    }
    context = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"context": context}


def build_observer_messages(state: Mapping[str, Any]) -> list[BaseMessage]:
    """Build the message list for the observer agent invocation."""
    messages: list[BaseMessage] = [SystemMessage(content=load_prompt("observer_system.md"))]

    history = state.get("messages") or state.get("chat_history")
    if history:
        messages.extend(_coerce_messages(history))
    else:
        if state.get("last_interviewer_message"):
            messages.append(AIMessage(content=str(state["last_interviewer_message"])))
        if state.get("last_user_message"):
            messages.append(HumanMessage(content=str(state["last_user_message"])))

    context = {
        "intake": _compact_intake(state.get("intake")),
        "topic": state.get("topic"),
        "difficulty": state.get("difficulty"),
        "planned_topics": state.get("planned_topics") or [],
        "current_topic_index": state.get("current_topic_index") or 0,
        "current_topic": _topic_from_plan(state),
        "agent_visible_message": state.get("last_interviewer_message") or "",
        "user_message": state.get("last_user_message") or "",
        "kickoff": not bool((state.get("last_user_message") or "").strip()),
        "recent_turns": _compact_turns(state.get("turns")),
    }
    context = _truncate_strings(context, _MAX_CONTEXT_STRING_LEN)
    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    messages.append(HumanMessage(content=f"Context (JSON):\n{context_text}"))

    return messages


def _topic_from_plan(state: Mapping[str, Any]) -> str | None:
    planned_topics = state.get("planned_topics") or []
    current_index = int(state.get("current_topic_index") or 0)
    if current_index < 0 or current_index >= len(planned_topics):
        return None
    topic = str(planned_topics[current_index]).strip()
    return topic or None


def build_report_messages(state: Mapping[str, Any]) -> list[BaseMessage]:
    """Build the message list for the report agent invocation."""
    payload = {
        "intake": _serialize(state.get("intake")),
        "skill_matrix": _serialize(state.get("skill_matrix")),
        "turns": _serialize(state.get("turns")),
        "observer_reports": _serialize(state.get("observer_reports")),
        "summary_notes": state.get("summary_notes"),
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return [
        SystemMessage(content=load_prompt("report_writer_system.md")),
        HumanMessage(content=content),
    ]


def build_planner_messages(state: Mapping[str, Any]) -> list[BaseMessage]:
    """Build the message list for the planner agent invocation."""
    context = {"intake_data": _compact_intake(state.get("intake"))}
    context = _truncate_strings(context, _MAX_CONTEXT_STRING_LEN)
    content = json.dumps(context, ensure_ascii=False, indent=2)
    return [
        SystemMessage(content=load_prompt("planner_system.md")),
        HumanMessage(content=content),
    ]


def get_interviewer_runnable(model: str, temperature: float, max_retries: int) -> Any:
    """Return a cached interviewer runnable pipeline."""
    key = (model, temperature, max_retries)
    if key not in _INTERVIEWER_CACHE:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("interviewer_system.md")),
                ("human", "{context}"),
            ]
        )
        _INTERVIEWER_CACHE[key] = prompt | build_model(*key) | StrOutputParser()
    return _INTERVIEWER_CACHE[key]


def get_observer_agent(model: str, temperature: float, max_retries: int) -> Any:
    """Return a cached observer agent."""
    key = (model, temperature, max_retries)
    if key not in _OBSERVER_CACHE:
        _OBSERVER_CACHE[key] = create_agent(
            build_model(*key),
            response_format=ObserverOutput,
        )
    return _OBSERVER_CACHE[key]


def get_report_agent(model: str, temperature: float, max_retries: int) -> Any:
    """Return a cached report agent."""
    key = (model, temperature, max_retries)
    if key not in _REPORT_CACHE:
        _REPORT_CACHE[key] = create_agent(
            build_model(*key),
            response_format=FinalFeedback,
        )
    return _REPORT_CACHE[key]


def get_planner_agent(model: str, temperature: float, max_retries: int) -> Any:
    """Return a cached planner agent."""
    key = (model, temperature, max_retries)
    if key not in _PLANNER_CACHE:
        _PLANNER_CACHE[key] = create_agent(
            build_model(*key),
            response_format=PlannedTopics,
        )
    return _PLANNER_CACHE[key]


def _tail(value: Any, limit: int = 5) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value[-limit:]
    return [value]


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, BaseMessage):
        return {"role": value.type, "content": value.content}
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    trimmed = value[:limit].rstrip()
    return f"{trimmed}..."


def _truncate_strings(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, limit)
    if isinstance(value, dict):
        return {key: _truncate_strings(val, limit) for key, val in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(item, limit) for item in value]
    return value


def _compact_intake(value: Any) -> Any:
    data = _serialize(value)
    if not isinstance(data, dict):
        if isinstance(data, str):
            return _truncate_text(data, _MAX_CONTEXT_STRING_LEN)
        return data
    allowed = ("participant_name", "position", "grade_target", "experience_summary")
    compact = {key: data.get(key) for key in allowed if key in data}
    if "experience_summary" in compact and compact["experience_summary"] is not None:
        compact["experience_summary"] = _truncate_text(str(compact["experience_summary"]), _MAX_CONTEXT_STRING_LEN)
    return compact


def _compact_turns(value: Any) -> list[dict[str, Any]]:
    turns = _tail(value)
    compacted: list[dict[str, Any]] = []
    for turn in turns:
        data = _serialize(turn)
        if isinstance(data, dict):
            compact: dict[str, Any] = {}
            for key in ("turn_id", "agent_visible_message", "user_message"):
                if key in data:
                    compact[key] = data[key]
            if compact:
                compacted.append(compact)
                continue
        compacted.append({"text": _truncate_text(str(data), _MAX_CONTEXT_STRING_LEN)})
    return compacted


def _coerce_messages(messages: Iterable[Any]) -> list[BaseMessage]:
    normalized: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, BaseMessage):
            normalized.append(message)
            continue
        if isinstance(message, dict):
            role = message.get("role")
            content = message.get("content", "")
            normalized.append(_message_from_role(role, content))
            continue
        normalized.append(HumanMessage(content=str(message)))
    return normalized


def _message_from_role(role: Any, content: Any) -> BaseMessage:
    role_value = str(role).lower() if role is not None else ""
    text = "" if content is None else str(content)
    if role_value in {"system", "sys"}:
        return SystemMessage(content=text)
    if role_value in {"assistant", "ai"}:
        return AIMessage(content=text)
    return HumanMessage(content=text)
