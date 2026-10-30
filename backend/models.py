from datetime import datetime, timedelta, timezone
from typing import Any, Optional

MOSCOW_TZ = timezone(timedelta(hours=3))

VALID_KINDS = {"task", "reminder", "meeting"}
VALID_STATUSES = {"open", "done"}
VALID_ACTIONS = {
    "create_task",
    "create_meeting",
    "list_events",
    "search_events",
    "clarify",
}


def now_moscow_iso() -> str:
    """Возвращает текущее время в ISO 8601 со смещением +03:00."""
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def is_valid_iso_datetime(value: Any) -> bool:
    """Проверяет, что строка является корректной ISO-датой со временем."""
    if not isinstance(value, str) or not value.strip():
        return False
    if "T" not in value and " " not in value:
        return False
    try:
        datetime.fromisoformat(value.strip())
        return True
    except ValueError:
        return False


def normalize_iso_datetime(value: str) -> str:
    """Приводит ISO-дату со временем к часовому поясу Europe/Moscow (+03:00)."""
    dt = datetime.fromisoformat(value.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    else:
        dt = dt.astimezone(MOSCOW_TZ)
    return dt.isoformat(timespec="seconds")


def is_valid_due_date(value: Any) -> bool:
    """Проверяет строгий формат даты YYYY-MM-DD без времени."""
    if not isinstance(value, str) or len(value.strip()) != 10:
        return False
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def row_to_event_dict(row: Any) -> dict[str, Any]:
    """Преобразует строку из БД в словарь по контракту команды."""
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "scheduled_at": row["scheduled_at"],
        "due_date": row["due_date"],
        "created_at": row["created_at"],
        "status": row["status"],
    }


def make_result(
    ok: bool,
    message: str,
    event: Optional[dict[str, Any]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    error_code: Optional[str] = None,
    needs_clarification: bool = False,
    missing_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Формирует единую структуру ответа backend.execute_intent."""
    return {
        "ok": ok,
        "message": message,
        "event": event,
        "events": events if events is not None else [],
        "error_code": error_code,
        "needs_clarification": needs_clarification,
        "missing_fields": missing_fields if missing_fields is not None else [],
    }