# AGENTS.md

## 1) Mission / Scope
- Проект: **Multi-Agent Interview Coach**
- Требования ТЗ: **2+ роли** (Interviewer + Observer), **hidden reflection**, **context awareness**, **adaptability**, **robustness**, **финальный отчёт**

## 2) Repo Structure
- `src/interview_coach/` — основной пакет
  - `__init__.py`
  - `agents.py` — сборка агентов и подготовка сообщений
  - `models.py` — Pydantic модели
  - `logger.py` — интервью-логгер
  - `prompts.py` — загрузка промптов из `prompts/`
  - `nodes/` — узлы графа
    - `difficulty.py`
    - `interviewer.py`
    - `observer.py`
- `prompts/`
  - `interviewer_system.md`
  - `observer_system.md`
  - `report_writer_system.md`
- `examples/scenarios/` — json/yaml сценарии для прогонов
- `runs/` — сгенерированные логи
- `tests/` — smoke tests
- `pyproject.toml` — ruff, mypy, pytest конфиг
- `README.md`

## 3) Code Style & Quality
- PEP8, строгая типизация (mypy-friendly), **Pydantic v2**
- **ruff format** и **ruff check** — основной инструмент качества
- Запрет на “god file”: модули небольшие, функции короткие
- Никакой магии: **явные модели, явные enums, явные контракты**

## 4) LangChain / LangGraph Principles
- Роли реализуем как **LangChain agents / runnables**
- **Structured output** получаем через `create_agent(response_format=...)` и читаем из `structured_response` (без ручного парсинга)
- Оркестрация диалога и hidden reflection — в **LangGraph StateGraph** (узлы `State -> Partial[State]`, граф `compile`)

## 5) Prompting Rules (важно для зачёта)
- НЕ один большой промпт: **строго отдельные агенты и отдельные prompt-файлы**
- **Observer возвращает строго JSON по схеме** (никакой “лирики”)
- **Interviewer не делает факт-чек и не выставляет оценку**
- **Hidden reflection**: перед каждым видимым ответом Interviewer должен опираться на скрытый отчёт Observer/Manager, и это отражено в `internal_thoughts` лога

## 6) Logging Contract
- `interview_log.json` обязателен
- Каждый `turn` содержит:
  - `turn_id`
  - `agent_visible_message`
  - `user_message`
  - `internal_thoughts` в формате: `"[Observer]: ... [Interviewer]: ..."`
- Логи читаемые: без гигантских “простыней”, но достаточно информативные
- `interview_log.json` совместим с ТЗ, `internal_thoughts` читаемый

## 7) CLI / UX
- Команда стопа: **"стоп"**, **"стоп интервью"**, **"stop"**
- После стопа генерируется **финальный отчёт** по структуре ТЗ

## 8) Definition of Done
- `ruff format` и `ruff check` проходят
- `pytest` проходит
- Есть минимум 1 пример прогона в `runs/` (sample log)
- `README.md` объясняет, как запустить
