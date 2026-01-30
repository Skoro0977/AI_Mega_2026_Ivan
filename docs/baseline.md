# Baseline (текущее состояние кода)

## 1) Граф (узлы + переходы)
Источник: `src/interview_coach/graph.py:111-164`.

**Узлы**
- `intake` -> `_run_intake` (пустой узел). `src/interview_coach/graph.py:94-99,116`
- `planner` -> `run_planner`. `src/interview_coach/graph.py:117`
- `observer` -> `run_observer`. `src/interview_coach/graph.py:118`
- `experts_router` -> `_run_intake` (пустой узел-роутер). `src/interview_coach/graph.py:119`
- `expert_*` -> `create_expert_node(role)`. `src/interview_coach/graph.py:120-124`
- `interviewer` -> `run_interviewer`. `src/interview_coach/graph.py:125`
- `wait_for_user_input` -> `_wait_for_user_input` (пустой узел). `src/interview_coach/graph.py:126`
- `final_report` -> `run_report`. `src/interview_coach/graph.py:127`

**Переходы**
- `intake -> planner -> observer`. `src/interview_coach/graph.py:131-132`
- После `observer` условный роут: `final_report | experts_router | interviewer`. `src/interview_coach/graph.py:134-142`
- После `experts_router` условный роут: `interviewer | expert_*` (по `pending_expert_nodes`). `src/interview_coach/graph.py:144-155`
- Любой `expert_* -> experts_router`. `src/interview_coach/graph.py:157-158`
- `interviewer -> wait_for_user_input -> END`. `src/interview_coach/graph.py:160-161`
- `final_report -> END`. `src/interview_coach/graph.py:162`

**Условия финализации**
- `_should_finalize` = stop или `current_topic_index >= 10` и `last_observer_report.recommended_next_action` в `{WRAP_UP, CHANGE_TOPIC}`. `src/interview_coach/graph.py:82-91`

## 2) Откуда берётся `internal_thoughts`
- Формируется в `run_interviewer` через `_build_internal_thoughts(...)` и кладётся в `pending_internal_thoughts`. `src/interview_coach/nodes/interviewer.py:64-94,224-246`
- Состав: `[Observer]: ...` (из `ObserverReport`) + `[Expert:*]: ...` (из экспертных заметок) + `[Interviewer]: strategy=...`. `src/interview_coach/nodes/interviewer.py:224-259`
- Записывается в `TurnLog` в `run_observer` при обработке `pending_*` полей. `src/interview_coach/nodes/observer.py:74-154`
- В `interview_log.json` попадает только из `TurnLog.internal_thoughts` в логгере. `src/interview_coach/logger.py:46-52`

## 3) ObserverReport: где формируется и какие поля используются
**Модель**
- Поля: `detected_topic`, `answer_quality`, `confidence`, `flags`, `recommended_next_action`, `recommended_question_style`, `fact_check_notes`, `skills_delta`. `src/interview_coach/models.py:161-171`

**Где формируется**
- `run_observer` строит `ObserverReport` локально в `_build_report(...)` (на основании `ObserverRoutingDecision`). `src/interview_coach/nodes/observer.py:112-231`
- `ObserverRoutingDecision` приходит от LLM-агента (модель: `src/interview_coach/models.py:204-221`), но сам `ObserverReport` LLM не генерирует. `src/interview_coach/nodes/observer.py:90-116`

**Где и что реально используется**
- `recommended_next_action`:
  - стратегию интервьюера (`deepen/change_topic/wrap_up`). `src/interview_coach/nodes/interviewer.py:104-121`
  - вычисление `advance_topic` в payload. `src/interview_coach/nodes/interviewer.py:134-156`
  - финализация графа (`_should_finalize`). `src/interview_coach/graph.py:82-91`
- `flags`:
  - выбор стратегии (off_topic -> return_to_topic). `src/interview_coach/nodes/interviewer.py:110-113`
  - пишется в `TurnLog.flags` для логов. `src/interview_coach/nodes/observer.py:144-154`
  - проверка в `run_difficulty` (off_topic/hallucination/role_reversal). `src/interview_coach/nodes/difficulty.py:39-42`
- `detected_topic`: лог (`TurnLog.topic`) и `topics_covered`. `src/interview_coach/nodes/observer.py:144-163`
- `skills_delta`: пишется в `TurnLog.skills_delta`. `src/interview_coach/nodes/observer.py:152-154`
- `answer_quality`: используется в `run_difficulty` (если бы был включён). `src/interview_coach/nodes/difficulty.py:49-53`
- `confidence`, `recommended_question_style`, `fact_check_notes` — сейчас нигде явно не используются вне модели.

## 4) Где пишется `interview_log.json` и что попадает в `final_feedback`
**Запись логов**
- Логи пишутся через `InterviewLogger.save(...)` в `runs/interview_log_*.json`. `src/interview_coach/cli.py:124-138,196-198`
- `InterviewLogger.save` формирует payload: `participant_name`, `turns`, `final_feedback` и валидирует схему. `src/interview_coach/logger.py:31-43,65-102`

**Состав `turns`**
- Только `turn_id`, `agent_visible_message`, `user_message`, `internal_thoughts`. `src/interview_coach/logger.py:46-52`

**Как формируется `final_feedback`**
- В CLI `_resolve_final_feedback` предпочитает `final_feedback_text` (суммарный текст), далее `final_feedback` как строку или `str(...)`. `src/interview_coach/cli.py:145-154`
- В `run_report` возвращается `final_feedback` (структурный `FinalFeedback`, модель: `src/interview_coach/models.py:266-272`) и `final_feedback_text` (суммарный текст). `src/interview_coach/nodes/report.py:61-65,98-128`
- В логгер записывается именно строка, полученная из `_resolve_final_feedback`. `src/interview_coach/cli.py:157-166`
- Если передать в логгер модель/словарь напрямую, он сериализует их в JSON-строку. `src/interview_coach/logger.py:55-62`

## 5) Почему требования сейчас не выполняются (критичные несоответствия)
- **Robustness flags**: флаги `off_topic/hallucination/contradiction/role_reversal` в `ObserverReport` не детектируются LLM и в `_build_report` выставляются в основном в `False` (кроме `ask_deeper`). `src/interview_coach/nodes/observer.py:200-231`
- **Kickoff reflection**: первый ответ интервьюера может формироваться без `ObserverReport` (нет `last_user_message`, `run_observer` выходит early), поэтому `internal_thoughts` = `[Observer]: no report.`. `src/interview_coach/nodes/observer.py:86-88`, `src/interview_coach/nodes/interviewer.py:224-232`
- **Difficulty wiring**: узел `run_difficulty` существует, но не добавлен в граф и никогда не вызывается. `src/interview_coach/nodes/difficulty.py:30-60` + отсутствие в `src/interview_coach/graph.py:111-162`
- **Context JSON drop**: если в `state` есть `messages` или `chat_history`, `build_observer_messages` возвращает историю и не добавляет JSON-контекст (intake/difficulty/plan). `src/interview_coach/agents.py:64-88`
- **final_feedback JSON vs text**: CLI всегда пишет строковый summary (`final_feedback_text`) в лог, а структурный `FinalFeedback` теряется (или превращается в `str(...)`). `src/interview_coach/cli.py:145-166`

## TODO (кратко)
- Включить `run_difficulty` в граф и провести `difficulty` через `pending_difficulty` корректно.
- Добавить полноценный `ObserverReport` (LLM output) или заполнение флагов/полей из наблюдателя.
- Гарантировать kickoff reflection перед первым вопросом (например, synthetic observer report на старте).
- Не терять JSON-контекст для observer при наличии history (добавлять context message или merge).
- Согласовать формат `final_feedback` в логах: хранить JSON + human-readable текст отдельно.
