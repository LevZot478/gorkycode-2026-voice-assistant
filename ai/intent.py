import re
import json
import requests
import os
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta


MODEL = "qwen3:4b"
OLLAMA_URL = "http://localhost:11434/api/chat"


SYSTEM_PROMPT = """
Ты — AI-ассистент для управления задачами, напоминаниями и встречами.

Твоя задача — определить намерение пользователя и вернуть строго JSON.
Не добавляй пояснений, Markdown и текста вне JSON.

JSON должен содержать ровно 9 ключей:
{
    "action": null,
    "title": null,
    "date_time": null,
    "period_start": null,
    "period_end": null,
    "query": null,
    "missing_fields": [],
    "kind": null,
    "due_date": null
}

Допустимые action:
- create_task
- create_meeting
- list_events
- search_events
- clarify

Допустимые kind:
- task
- reminder
- meeting
- null

ПРАВИЛА ВЫБОРА ДЕЙСТВИЯ:

1. Если пользователь сообщает, что ему нужно что-то сделать, выбирай create_task.
2. Если пользователь просит создать напоминание, выбирай create_task и kind="reminder".
3. Если пользователь просит добавить встречу или созвон, выбирай create_meeting.
4. Если пользователь спрашивает о запланированных событиях, выбирай list_events.
5. Если пользователь просит найти конкретное событие, выбирай search_events.
6. Используй clarify только тогда, когда невозможно определить намерение или не хватает обязательной информации для встречи.

ПРАВИЛА ДЛЯ ЗАДАЧ:

- Для обычной задачи используй kind="task".
- Для напоминания используй kind="reminder".
- Если пользователь назвал действие, обязательно заполни title кратким названием этого действия.
- Время для обычной задачи необязательно.
- Если дата указана, но время не указано:
  - date_time = null
  - due_date = дата в формате YYYY-MM-DD
  - missing_fields = []
- Если указаны дата и время:
  - date_time = дата и время в ISO 8601 со смещением +03:00
  - due_date = null
- Не требуй date_time для обычных задач.
- Не выдумывай дату и время.

ПРАВИЛА ДЛЯ ВСТРЕЧ:

- Для встречи используй action="create_meeting" и kind="meeting".
- Встреча обязательно должна иметь дату и время.
- Если дата или время встречи отсутствует, используй action="clarify".
- В missing_fields укажи недостающую информацию.
- Если пользователь указал дату встречи, но не указал время:
  - action = "clarify"
  - date_time = null
  - missing_fields = ["время"]
  - kind = "meeting"
- Никогда не подставляй 00:00, если время не указано пользователем.

ПРАВИЛА ДЛЯ ПРОСМОТРА:

Для list_events:

- period_start и period_end обязательны.
- Всегда вычисляй период относительно текущей даты из now_iso.
- Используй формат ISO 8601 со смещением +03:00.
- period_end — исключительная граница периода.

Если пользователь спрашивает:

- «Что у меня сегодня?» — период от 00:00 сегодняшнего дня до 00:00 завтрашнего дня.
- «Что у меня завтра?» — период от 00:00 завтрашнего дня до 00:00 послезавтрашнего дня.
- «Что у меня послезавтра?» — период от 00:00 послезавтрашнего дня до 00:00 следующего дня.
- «Что у меня на этой неделе?» — период с понедельника текущей недели до понедельника следующей недели.

Для list_events нельзя оставлять period_start и period_end равными null, если период можно определить из запроса.

Для search_events:
- query — краткий поисковый запрос.

ОБЩИЕ ПРАВИЛА:

- Учитывай текущее время, переданное в сообщении пользователя.
- Интерпретируй слова «сегодня», «завтра», «послезавтра» и дни недели относительно текущей даты.
- Используй московский часовой пояс UTC+03:00.
- Все неприменимые поля должны быть null.
- missing_fields всегда должен быть списком.
- Не добавляй лишние ключи.

ПРИМЕРЫ:

Текущее время: 2026-10-31T13:00:00+03:00
Запрос: В субботу нужно отправить отчёт.

Ответ:
{
    "action": "create_task",
    "title": "Отправить отчёт",
    "date_time": null,
    "period_start": null,
    "period_end": null,
    "query": null,
    "missing_fields": [],
    "kind": "task",
    "due_date": "2026-10-31"
}

Текущее время: 2026-10-31T13:00:00+03:00
Запрос: Создай напоминание завтра в 10 позвонить маме.

Ответ:
{
    "action": "create_task",
    "title": "Позвонить маме",
    "date_time": "2026-11-01T10:00:00+03:00",
    "period_start": null,
    "period_end": null,
    "query": null,
    "missing_fields": [],
    "kind": "reminder",
    "due_date": null
}

Текущее время: 2026-10-31T13:00:00+03:00
Запрос: Добавь встречу завтра в 15:00.

Ответ:
{
    "action": "create_meeting",
    "title": "Встреча",
    "date_time": "2026-11-01T15:00:00+03:00",
    "period_start": null,
    "period_end": null,
    "query": null,
    "missing_fields": [],
    "kind": "meeting",
    "due_date": null
}
"""

def _weekday_date(text: str, now_iso: str):
    """Возвращает ближайшую дату указанного дня недели или None."""
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "сред": 2,
        "четверг": 3,
        "пятниц": 4,
        "суббот": 5,
        "воскресень": 6,
    }

    match = re.search(
        r"\b(понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)\b",
        text.lower()
    )
    if not match:
        return None

    weekday_word = match.group(1)
    target_weekday = next(
        day for prefix, day in weekdays.items()
        if weekday_word.startswith(prefix)
    )

    current_date = datetime.fromisoformat(now_iso).date()
    days_ahead = (target_weekday - current_date.weekday()) % 7

    if days_ahead == 0 and re.search(r"\bследующ\w*\b", text.lower()):
        days_ahead = 7

    return current_date + timedelta(days=days_ahead)


REQUIRED_KEYS = {
    "action",
    "title",
    "date_time",
    "period_start",
    "period_end",
    "query",
    "missing_fields",
    "kind",
    "due_date"
}


def parse_intent(text: str, now_iso: str) -> dict:
    """
    Преобразует текст пользователя в структурированный JSON.
    """

    # Нормализация фразы «после завтра»
    text = re.sub(
        r"\bпосле\s+завтра\b",
        "послезавтра",
        text,
        flags=re.IGNORECASE
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Текущее время: {now_iso}\nЗапрос: {text}"}
    ]
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                  "messages": messages, "temperature": 0,
                  "response_format": {"type": "json_object"}},
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    else:
        response = requests.post(
            os.getenv("OLLAMA_URL", OLLAMA_URL),
            json={"model": os.getenv("OLLAMA_MODEL", MODEL),
                  "messages": messages, "stream": False, "think": False,
                  "format": "json", "options": {"temperature": 0}},
            timeout=120
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]

    intent = json.loads(content)

    if set(intent.keys()) != REQUIRED_KEYS:
        raise ValueError("Модель вернула неправильную структуру JSON")

    if not isinstance(intent["missing_fields"], list):
        raise ValueError("missing_fields должен быть списком")

    # Дату дня недели вычисляем средствами Python, а не доверяем модели.
    if intent["action"] == "create_task":
        weekday_date = _weekday_date(text, now_iso)
        if weekday_date is not None:
            if intent["date_time"]:
                parsed_datetime = datetime.fromisoformat(intent["date_time"])
                intent["date_time"] = parsed_datetime.replace(
                    year=weekday_date.year,
                    month=weekday_date.month,
                    day=weekday_date.day
                ).isoformat()
                intent["due_date"] = None
            else:
                intent["due_date"] = weekday_date.isoformat()

    return intent 