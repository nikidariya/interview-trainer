"""Роль 3. Ход интервью: решает, какой агент вызывается следующим."""
from app.agents import analyst, coach, evaluator, interviewer
from app.schemas import AnswerScore, InterviewPlan, Turn


class InterviewSession:
    """Состояние одного интервью хранится прямо в объекте, в памяти."""

    def __init__(self) -> None:
        self.plan: InterviewPlan | None = None
        self.history: list[Turn] = []
        self.scores: list[AnswerScore] = []
        self.topic_index = 0
        self._current_question = ""

    def start(self, vacancy_text: str) -> str:
        """Принимает текст вакансии, возвращает первый вопрос."""
        self.plan = analyst.build_plan(vacancy_text)
        self._current_question = interviewer.next_question(self.plan, self.history, self.topic_index)
        return self._current_question

    def submit_answer(self, answer: str) -> str | None:
        """Принимает ответ пользователя. Возвращает следующий вопрос или None, если интервью закончено."""
        self.history.append(Turn(question=self._current_question, answer=answer))
        self.scores.append(evaluator.score_answer(self._current_question, answer))
        self.topic_index += 1
        if self.topic_index >= len(self.plan.topics):
            return None
        self._current_question = interviewer.next_question(self.plan, self.history, self.topic_index)
        return self._current_question

    def report(self) -> str:
        """Итоговый разбор после окончания интервью."""
        return coach.final_report(self.plan, self.history, self.scores)
