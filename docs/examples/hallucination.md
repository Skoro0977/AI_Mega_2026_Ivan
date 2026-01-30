# Hallucination mini-run

**Context:** current_topic = "Kafka", difficulty=HARD.

1) Interviewer: Как вы настраивали ретеншн и партиционирование в Kafka?
2) Candidate: В Kafka нет брокеров, там только клиенты, поэтому ретеншн не нужен.
3) Interviewer (expected): Кажется, тут есть неточность. Можете уточнить, на чём основано это утверждение? Если не уверены, можно так и сказать. Как вы тогда настраивали ретеншн и партиции?

**Expected internal_thoughts excerpt:**
- [Observer]: ... hallucination=True ... next_action=HANDLE_HALLUCINATION ...
- [Interviewer]: ... strategy=challenge_hallucination ...

**Acceptance check:** interviewer просит обоснование/уточнение и возвращает к теме.
