# Off-topic mini-run

**Context:** current_topic = "Базы данных", difficulty=MEDIUM.

1) Interviewer: Расскажите, как вы проектируете индексы в PostgreSQL?
2) Candidate: На выходных в Питере была отличная погода, мы гуляли весь день.
3) Interviewer (expected): Понимаю, приятно. Вернёмся к теме: как вы выбираете индексы в PostgreSQL?

**Expected internal_thoughts excerpt:**
- [Observer]: ... off_topic=True ... next_action=HANDLE_OFFTOPIC ...
- [Interviewer]: ... strategy=return_to_topic ...

**Acceptance check:** interviewer explicitly возвращает к вопросу, не обсуждает погоду.
