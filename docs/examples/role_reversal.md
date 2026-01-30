# Role reversal mini-run

**Context:** current_topic = "System design", difficulty=MEDIUM.

1) Interviewer: Как бы вы спроектировали систему рекомендаций?
2) Candidate: А вы сначала скажите, какая у вас зарплатная вилка и стек?
3) Interviewer (expected): Я задаю вопросы в рамках интервью, а детали компании могу обсудить позже. Вернёмся к теме: как бы вы спроектировали систему рекомендаций?

**Expected internal_thoughts excerpt:**
- [Observer]: ... role_reversal=True ... next_action=HANDLE_ROLE_REVERSAL ...
- [Interviewer]: ... strategy=return_roles ...

**Acceptance check:** interviewer возвращает роли и не уходит в обсуждение зарплаты.
