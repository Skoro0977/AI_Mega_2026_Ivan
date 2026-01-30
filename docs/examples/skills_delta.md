# Skills delta example

**Turn 1 (good answer)**
- ObserverOutput.skills_delta:
  - { skill: "queues", delta: +0.8, evidence_turn_id: 1, note: "Корректно объяснил ack/retry" }
- skill_matrix["queues"].score: 0.0 -> 0.8
- skill_snapshot.confirmed includes "queues" once score >= threshold

**Turn 2 (mistake)**
- ObserverOutput.skills_delta:
  - { skill: "db_modeling", delta: -0.6, evidence_turn_id: 2, note: "Смешал нормализацию и денормализацию" }
- skill_matrix["db_modeling"].score: 0.4 -> -0.2 (clamped to 0.0)
- skill_snapshot.gaps includes "db_modeling" when score <= threshold

**Expected in report context:**
- skill_snapshot.confirmed/gaps + evidence per skill.
