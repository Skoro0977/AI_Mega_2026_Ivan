# Пример: изменение навыков (skills_delta)

**Ход 1 (хороший ответ)**
- ObserverOutput.skills_delta:
  - { skill: "queues", delta: +0.8, evidence_turn_id: 1, note: "Корректно объяснил ack/retry" }
- skill_matrix["queues"].score: 0.0 -> 0.8
- skill_snapshot.confirmed включает "queues", когда score >= threshold

**Ход 2 (ошибка)**
- ObserverOutput.skills_delta:
  - { skill: "db_modeling", delta: -0.6, evidence_turn_id: 2, note: "Смешал нормализацию и денормализацию" }
- skill_matrix["db_modeling"].score: 0.4 -> -0.2 (clamped to 0.0)
- skill_snapshot.gaps включает "db_modeling", когда score <= threshold

**Ожидаемо в контексте отчёта:**
- skill_snapshot.confirmed/gaps + evidence по каждому навыку.
