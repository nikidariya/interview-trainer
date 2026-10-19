"""Роль 3. Ход интервью: решает, какой агент вызывается следующим """
from app.agents import analyst, coach, evaluator, interviewer
from app.schemas import AnswerScore, InterviewPlan, Turn

# Если конкретика ниже этого порога, интервьюер задаёт один уточняющий вопрос
CLARIFY_THRESHOLD = 3


class InterviewSession:
    """Состояние одного интервью хранится прямо в объекте, в памяти"""

    def __init__(self) -> None:
        self.plan: InterviewPlan | None = None
        self.history: list[Turn] = []
        self.scores: list[AnswerScore] = []
        self.topic_index = 0
        self._current_question = ""
        self._clarified = False  # задавали ли уже уточнение по текущей теме

    def start(self, vacancy_text: str) -> str:
        """Принимает текст вакансии, возвращает первый вопрос"""
        plan = analyst.build_plan(vacancy_text)
        question = interviewer.next_question(plan, self.history, self.topic_index)
        # Состояние меняем только после того, как оба агента ответили без ошибок
        self.plan = plan
        self._current_question = question
        return question

    def submit_answer(self, answer: str) -> str | None:
        """Принимает ответ пользователя. Возвращает следующий вопрос или None, если интервью закончено"""
        # Шаг 1: все вызовы агентов. Если один из них упадёт, состояние останется прежним
        score = evaluator.score_answer(self._current_question, answer)
        history = self.history + [Turn(question=self._current_question, answer=answer)]

        need_clarify = (
            score.scores.get("Конкретика", CLARIFY_THRESHOLD) < CLARIFY_THRESHOLD
            and not self._clarified
        )
        if need_clarify:
            topic_index = self.topic_index  # остаёмся на той же теме
            next_question = interviewer.next_question(self.plan, history, topic_index, clarify=True)
        else:
            topic_index = self.topic_index + 1
            if topic_index >= len(self.plan.topics):
                next_question = None
            else:
                next_question = interviewer.next_question(self.plan, history, topic_index)

        # Шаг 2: ничего не упало, теперь записываем результат
        self.history = history
        self.scores.append(score)
        self.topic_index = topic_index
        self._clarified = need_clarify
        if next_question is not None:
            self._current_question = next_question
        return next_question

    def report(self) -> str:
        """Итоговый разбор после окончания интервью"""
        return coach.final_report(self.plan, self.history, self.scores)