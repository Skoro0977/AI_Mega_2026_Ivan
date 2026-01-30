# Multi-Agent Interview Coach

Проект: **Multi-Agent Interview Coach** — многоагентный тренер интервью с двумя ролями (Interviewer + Observer), скрытой рефлексией и финальным отчётом.

## Архитектура (коротко)
- **LangGraph StateGraph** управляет диалогом и маршрутизацией узлов.
- **Interviewer** генерирует видимые вопросы/ответы и опирается на скрытый отчёт Observer.
- **Observer** возвращает строго структурированный JSON (Pydantic v2) с оценкой и флагами.
- **Difficulty node** корректирует сложность по сигналам Observer.
- **Report node** формирует финальный структурированный отчёт.
- **Logger** пишет `interview_log.json` с `internal_thoughts` по каждому ходу.

## Поток исполнения (StateGraph)
```puml
@startuml
title Interview Coach Graph
start
:router;
if (stop_requested?) then (yes)
  :final_report;
  stop
else (no)
  :observer;
  :difficulty;
  :interviewer;
  --> :router;
endif
@enduml
```

## Компоненты и ответственность
```puml
@startuml
title Components & Data Flow
actor Candidate
node "CLI / Scenario Runner" as cli
node "LangGraph StateGraph" as graph
component "Observer Agent\n(create_agent + ObserverReport)" as observer
component "Interviewer Runnable\n(prompt + model)" as interviewer
component "Report Agent\n(create_agent + FinalFeedback)" as report
component "Logger\n(interview_log.json)" as logger
database "runs/*.json" as runs

Candidate --> cli
cli --> graph
graph --> observer
graph --> interviewer
graph --> report
graph --> logger
logger --> runs
@enduml
```

## Как агент “думает”
- **Observer** получает историю и контекст, возвращает `ObserverReport` (строго JSON).
- **Interviewer** получает контекст + `ObserverReport` и выбирает стратегию (`deepen`, `simplify`, `wrap_up` и т.д.).
- **Hidden reflection** сохраняется в `TurnLog.internal_thoughts` в формате:
  `"[Observer]: ... [Interviewer]: ..."` — это обязателен контракт логов.

## Основные файлы
- `src/interview_coach/graph.py` — сборка графа и маршрутизация.
- `src/interview_coach/nodes/observer.py` — вызов Observer + обновление skill_matrix.
- `src/interview_coach/nodes/difficulty.py` — адаптация сложности (1..5).
- `src/interview_coach/nodes/interviewer.py` — генерация ответа и запись `TurnLog`.
- `src/interview_coach/nodes/report.py` — финальный отчёт.
- `src/interview_coach/agents.py` — фабрики моделей и агентов.
- `src/interview_coach/models.py` — Pydantic v2 модели (контракты).
- `src/interview_coach/logger.py` — запись `interview_log.json`.
- `prompts/*.md` — системные промпты агентов (строго раздельные).

## Контракты данных (Pydantic v2)
```puml
@startuml
title Core Models (simplified)
class ObserverReport {
  detected_topic: str
  answer_quality: float
  confidence: float
  flags: ObserverFlags
  recommended_next_action: NextAction
  recommended_question_style: str
  fact_check_notes: str?
  skills_delta: map?
}
class TurnLog {
  turn_id: int
  agent_visible_message: str
  user_message: str
  internal_thoughts: str
  topic: str?
  difficulty_before: int?
  difficulty_after: int?
  flags: ObserverFlags?
  skills_delta: map?
}
class FinalFeedback {
  decision: Decision
  hard_skills: HardSkillsFeedback
  soft_skills: SoftSkillsFeedback
  roadmap: Roadmap
}
ObserverReport --> ObserverFlags
FinalFeedback --> Decision
FinalFeedback --> HardSkillsFeedback
FinalFeedback --> SoftSkillsFeedback
FinalFeedback --> Roadmap
@enduml
```

## Как работает адаптация сложности
- Узел `difficulty` меняет уровень, если **answer_quality >= 4** (повышение) или **<= 2** (понижение).
- Если флаги `off_topic`, `hallucination`, `role_reversal` активны — сложность **не меняется**.

## Логи и формат
- Лог хранится в `runs/interview_log_*.json`.
- Каждый `turn` содержит `turn_id`, `agent_visible_message`, `user_message`, `internal_thoughts`.
- В `internal_thoughts` обязательно присутствуют данные Observer и выбранная стратегия Interviewer.

## Setup
```bash
uv venv
source .venv/bin/activate
uv sync
```

## Environment
Настройки читаются через `pydantic-settings` из переменных окружения и файла `.env` в корне проекта.

Поддерживаемые параметры:
```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.your-gateway.example/v1
```
Также поддерживается алиас `OPENAI_API_BASE` для base URL.

## Run CLI
```bash
uv run python -m interview_coach.cli
```

## Run Scenario
```bash
uv run python -m interview_coach.scenarios --scenario examples/scenarios/sample.json
```

## Run Tests
```bash
uv run pytest
```

## Output logs
```bash
ls runs/
```
