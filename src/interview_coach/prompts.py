"""Prompt loading helpers."""

from __future__ import annotations

from pathlib import Path


def load_prompt(name: str) -> str:
    prompt_name = name if name.endswith(".md") else f"{name}.md"
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    prompt_path = prompts_dir / prompt_name
    return prompt_path.read_text(encoding="utf-8")
