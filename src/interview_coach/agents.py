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

from src.interview_coach.models import FinalFeedback, ObserverReport
from src.interview_coach.prompts import load_prompt
from src.interview_coach.settings import get_settings

_ModelKey = tuple[str, float, int]

_MODEL_CACHE: dict[_ModelKey, ChatOpenAI] = {}
_INTERVIEWER_CACHE: dict[_ModelKey, Any] = {}
_OBSERVER_CACHE: dict[_ModelKey, Any] = {}
_REPORT_CACHE: dict[_ModelKey, Any] = {}


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
        return messages

    if state.get("last_interviewer_message"):
        messages.append(AIMessage(content=str(state["last_interviewer_message"])))
    if state.get("last_user_message"):
        messages.append(HumanMessage(content=str(state["last_user_message"])))

    context = _serialize(
        {
            "intake": _serialize(state.get("intake")),
            "topic": state.get("topic"),
            "difficulty": state.get("difficulty"),
            "recent_turns": _serialize(_tail(state.get("turns"))),
        }
    )
    if context:
        messages.append(HumanMessage(content=f"Context: {context}"))

    return messages


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
            response_format=ObserverReport,
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
