# Как работаем в репозитории

## Кто чем владеет
Чужие файлы не трогаем. Если нужно изменение в чужом файле, пишем владельцу.

| Роль | Файлы | Ветка |
|---|---|---|
| 1. Агенты-собеседники | `app/agents/analyst.py`, `app/agents/interviewer.py`, `prompts/analyst.md`, `prompts/interviewer.md`, `requirements/agents.txt` | `role1-agents` |
| 2. Оценка | `app/agents/evaluator.py`, `app/agents/coach.py`, `prompts/evaluator.md`, `prompts/coach.md`, `eval/`, `requirements/evaluation.txt` | `role2-evaluation` |
| 3. Ход интервью и интерфейс | `app/orchestrator.py`, `app/ui.py`, `requirements/ui.txt` | `role3-ui` |
| 4. Платформа | всё остальное: клиент GigaChat, `parsing.py`, Docker, README, `tests/`, `docs/` | `role4-platform` |

## Правила
1. Работаем только в своей ветке. В `main` вливаем через Pull Request, когда часть запускается.
2. Новые библиотеки добавляем в свой файл из `requirements/`.
3. Ключ GigaChat лежит только в локальном `.env`. Файл `.env` в git не попадает, в репозиторий кладём только `.env.example`.
