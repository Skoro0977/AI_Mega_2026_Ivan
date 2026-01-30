# Мини-прогон: галлюцинация

**Контекст:** current_topic = "Kafka", difficulty = HARD.

1) Interviewer: Как вы настраивали ретеншн и партиционирование в Kafka?
2) Candidate: В Kafka нет брокеров, там только клиенты, поэтому ретеншн не нужен.
3) Interviewer (ожидаемо): Кажется, тут есть неточность. Можете уточнить, на чём основано это утверждение? Если не уверены, можно так и сказать. Как вы тогда настраивали ретеншн и партиции?

**Ожидаемый фрагмент internal_thoughts:**
- [Observer]: ... hallucination=True ... next_action=HANDLE_HALLUCINATION ...
- [Interviewer]: ... strategy=challenge_hallucination ...

**Проверка:** интервьюер просит обоснование/уточнение и возвращает к теме.
