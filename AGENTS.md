# AGENTS.md

## 1) Repo Structure
- `src/interview_coach/` — основной пакет
  - `__init__.py`
  - `models.py` — Pydantic модели
  - `logger.py` — интервью-логгер
  - `llm.py` — LLM клиент/провайдер-агностик
  - `prompts.py` — загрузка промптов из `prompts/`
  - `graph.py` — LangGraph граф
  - `nodes/` — узлы графа
    - `interviewer.py`
    - `observer.py`
    - `difficulty.py`
    - `router.py`
    - `report.py`
  - `cli.py` — CLI runner
  - `scenarios.py` — скриптовые прогоны секретных сценариев
- `prompts/`
  - `interviewer_system.md`
  - `observer_system.md`
  - `report_writer_system.md`
- `examples/scenarios/` — json/yaml сценарии для прогонов
- `runs/` — сгенерированные логи
- `tests/` — smoke tests
- `pyproject.toml` — ruff, mypy, pytest конфиг
- `README.md`

## 2) Code Style & Quality
- PEP8, строгая типизация (mypy-friendly), **Pydantic v2**
- **ruff (lint + format)** — основной инструмент качества
- Запрет на “god file”: модули небольшие, функции короткие
- Никакой магии: **явные модели, явные enums, явные контракты**

## 3) Prompting Rules (важно для зачёта)
- НЕ один большой промпт: **строго отдельные агенты и отдельные prompt-файлы**
- **Observer возвращает строго JSON по схеме** (никакой “лирики”)
- **Interviewer не делает факт-чек и не выставляет оценку**
- **Hidden reflection**: перед каждым видимым ответом Interviewer должен опираться на скрытый отчёт Observer/Manager, и это отражено в `internal_thoughts` лога

## 4) Logging Contract
- `interview_log.json` обязателен
- Каждый `turn` содержит:
  - `turn_id`
  - `agent_visible_message`
  - `user_message`
  - `internal_thoughts` в формате: `"[Observer]: ... [Interviewer]: ..."`
- Логи читаемые: без гигантских “простыней”, но достаточно информативные

## 5) CLI / UX
- Команда стопа: **"стоп"**, **"стоп интервью"**, **"stop"**
- После стопа генерируется **финальный отчёт** по структуре ТЗ

## 6) Definition of Done
- `ruff format` и `ruff check` проходят
- `pytest` проходит
- Есть минимум 1 пример прогона в `runs/` (sample log)
- `README.md` объясняет, как запустить
