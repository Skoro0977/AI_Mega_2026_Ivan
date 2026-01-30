# Multi-Agent Interview Coach

Многоагентный тренер технических интервью с планированием тем, маршрутизацией через Observer, экспертными подсказками и финальным отчётом. Архитектура построена на LangGraph StateGraph, все ключевые ответы — structured output через Pydantic v2.

## Что умеет
- **Роли**: Planner, Observer, Interviewer, Expert (5 ролей), Report writer.
- **Hidden reflection**: внутренняя логика Observer/Interviewer сохраняется в `internal_thoughts` лога.
- **Контекстная адаптация**: маршрутизация по темам, выбор экспертов, защита от повторов вопросов.
- **Финальный отчёт**: структурированный `FinalFeedback` + читаемое резюме.
- **CLI и сценарии**: интерактивный режим и прогон скриптовых интервью.
- **Строгие контракты**: Pydantic v2 модели для всех structured outputs.

## Поток в графе
Текущий граф в `src/interview_coach/graph.py`:

```
intake -> planner -> observer -> (experts_router?) -> expert_* -> interviewer -> wait_for_user_input -> END
                                    \-> final_report -> END
```

- **Planner** строит план из **10 тем** (`PlannedTopics`).
- **Observer** возвращает **routing decision** (`ObserverRoutingDecision`) и формирует краткий `ObserverReport` для hidden reflection.
- **Experts** (tech lead / team lead / QA / designer / analyst) дают внутренние заметки для Interviewer.
- **Interviewer** генерирует следующий вопрос и обновляет `internal_thoughts`.
- **Report** формирует `FinalFeedback` при остановке.

Примечание: узел `difficulty` существует, но **сейчас не подключён** в граф (сложность фиксируется в состоянии как базовая).

## Основные компоненты
- `src/interview_coach/graph.py` — сборка графа.
- `src/interview_coach/agents.py` — модели и агенты (create_agent + structured outputs).
- `src/interview_coach/models.py` — все Pydantic контракты.
- `src/interview_coach/nodes/` — узлы графа (planner, observer, experts, interviewer, report).
- `src/interview_coach/cli.py` — интерактивный CLI.
- `src/interview_coach/scenarios.py` — сценарные прогоны.
- `src/interview_coach/logger.py` — формат логов.
- `prompts/*.md` — отдельные системные промпты по ролям.

## Контракты данных (кратко)
- `InterviewIntake`: имя, позиция, уровень, опыт.
- `PlannedTopics`: **ровно 10 тем**.
- `ObserverRoutingDecision`: `ask_deeper`, `advance_topic`, `expert_roles` (1–2 роли).
- `ObserverReport`: оценка ответа и next_action для скрытой рефлексии.
- `ExpertEvaluation`: комментарий + optional уточняющий вопрос.
- `FinalFeedback`: итоговая оценка (decision, hard/soft skills, roadmap).
- `TurnLog`: видимый текст + `internal_thoughts` в формате `"[Observer]: ... [Interviewer]: ..."`.

## Логи
Логи пишутся в `runs/` и имеют схему:
```
{
  "participant_name": "...",
  "turns": [
    {"turn_id": 1, "agent_visible_message": "...", "user_message": "...", "internal_thoughts": "..."}
  ],
  "final_feedback": "..."
}
```
`internal_thoughts` обязателен для каждого хода.

## Быстрый старт
### Установка
```bash
uv venv
source .venv/bin/activate
uv sync
```

### Переменные окружения
Поддерживаются (через `.env` или env):
```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.your-gateway.example/v1
```
Также поддерживается алиас `OPENAI_API_BASE`.

### Запуск CLI
```bash
uv run python -m src.interview_coach.cli --max-turns 12
```
Команды остановки: `stop`, `стоп`, `стоп интервью`.

### Запуск сценария
```bash
uv run python -m src.interview_coach.scenarios --scenario examples/scenarios/sample.json
```

## Качество и тесты
```bash
uv run ruff format
uv run ruff check
uv run pytest
```

## Примеры
- Сценарии: `examples/scenarios/`
- Логи прогонов: `runs/`

## Требования
- Python `>= 3.14`
- Pydantic v2, LangChain, LangGraph (см. `pyproject.toml`)
