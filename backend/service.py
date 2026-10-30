from difflib import SequenceMatcher
import re
from typing import Any, Optional

from backend.database import get_connection, init_db
from backend.models import (
    VALID_ACTIONS,
    VALID_KINDS,
    is_valid_due_date,
    is_valid_iso_datetime,
    make_result,
    normalize_iso_datetime,
    now_moscow_iso,
    row_to_event_dict,
)

SEARCH_STOP_WORDS = {
    "про", "по", "на", "в", "во", "с", "со", "к", "ко", "о", "об", "от", "до",
    "для", "из", "за", "над", "под", "при", "и", "а", "но", "или", "что", "как",
    "задача", "задачу", "задачи", "встреча", "встречу", "встречи",
    "напоминание", "напоминания", "событие", "события",
    "найди", "найти", "поищи", "покажи", "когда", "была", "был", "было",
    "меня", "мне", "мои", "моя", "мой", "у", "я", "когда-то", "ставил", "ставила",
}


def create_event(
    kind: str,
    title: str,
    scheduled_at: Optional[str] = None,
    due_date: Optional[str] = None,
) -> dict[str, Any]:
    """Валидирует поля и сохраняет запись в БД с автоинициализацией таблицы."""
    clean_title = title.strip() if isinstance(title, str) else ""
    if not clean_title:
        return make_result(
            ok=False,
            message="Не указано название задачи или встречи.",
            error_code="validation_error",
            needs_clarification=True,
            missing_fields=["title"],
        )

    if kind not in VALID_KINDS:
        return make_result(
            ok=False,
            message=f"Неизвестный тип записи: '{kind}'.",
            error_code="validation_error",
            missing_fields=["kind"],
        )

    if kind == "meeting":
        if not scheduled_at:
            return make_result(
                ok=False,
                message="На какое время поставить встречу?",
                error_code="validation_error",
                needs_clarification=True,
                missing_fields=["date_time"],
            )
        if not is_valid_iso_datetime(scheduled_at):
            return make_result(
                ok=False,
                message="Некорректный формат даты и времени встречи.",
                error_code="validation_error",
                missing_fields=["date_time"],
            )

    norm_scheduled_at: Optional[str] = None
    if scheduled_at is not None:
        if not is_valid_iso_datetime(scheduled_at):
            return make_result(
                ok=False,
                message="Некорректный формат поля date_time (ожидается ISO 8601).",
                error_code="validation_error",
                missing_fields=["date_time"],
            )
        norm_scheduled_at = normalize_iso_datetime(scheduled_at)

    norm_due_date: Optional[str] = None
    if due_date is not None:
        if not is_valid_due_date(due_date):
            return make_result(
                ok=False,
                message="Некорректный формат поля due_date (ожидается YYYY-MM-DD).",
                error_code="validation_error",
                missing_fields=["due_date"],
            )
        if norm_scheduled_at is None:
            norm_due_date = due_date.strip()

    created_at = now_moscow_iso()

    conn = None
    try:
        init_db()
        conn = get_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO events (kind, title, scheduled_at, due_date, created_at, status)
                VALUES (?, ?, ?, ?, ?, 'open')
                """,
                (kind, clean_title, norm_scheduled_at, norm_due_date, created_at),
            )
            event_id = cursor.lastrowid

        row = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        event_dict = row_to_event_dict(row)

        labels = {
            "task": f"Создана задача: «{clean_title}»",
            "reminder": f"Создано напоминание: «{clean_title}»",
            "meeting": f"Создана встреча: «{clean_title}»",
        }
        return make_result(
            ok=True,
            message=labels.get(kind, "Запись сохранена"),
            event=event_dict,
        )
    except Exception as exc:
        return make_result(
            ok=False,
            message=f"Ошибка базы данных при сохранении: {exc}",
            error_code="db_error",
        )
    finally:
        if conn is not None:
            conn.close()


def list_events(start: str, end: str) -> list[dict[str, Any]]:
    """Возвращает список событий за период [start, end)."""
    if not is_valid_iso_datetime(start) or not is_valid_iso_datetime(end):
        return []

    norm_start = normalize_iso_datetime(start)
    norm_end = normalize_iso_datetime(end)
    if norm_start >= norm_end:
        return []

    select_sql = """
    SELECT * FROM events
    WHERE
        (scheduled_at IS NOT NULL AND scheduled_at >= ? AND scheduled_at < ?)
        OR
        (
            scheduled_at IS NULL
            AND due_date IS NOT NULL
            AND (due_date || 'T00:00:00+03:00') >= ?
            AND (due_date || 'T00:00:00+03:00') < ?
        )
    ORDER BY COALESCE(scheduled_at, due_date || 'T00:00:00+03:00') ASC, id ASC
    """

    conn = None
    try:
        init_db()
        conn = get_connection()
        rows = conn.execute(
            select_sql, (norm_start, norm_end, norm_start, norm_end)
        ).fetchall()
        return [row_to_event_dict(r) for r in rows]
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()


def _normalize_text(text: str) -> str:
    cleaned = text.lower().replace("ё", "е")
    cleaned = re.sub(r"[^\w\s-]", " ", cleaned)
    return " ".join(cleaned.split())


def _stem_ru(word: str) -> str:
    if len(word) >= 7:
        return word[:-2]
    if len(word) >= 5:
        return word[:-1]
    return word


def search_events(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Ищет события по ключевым словам и нечеткому совпадению."""
    if not isinstance(query, str) or not query.strip():
        return []

    norm_query = _normalize_text(query)
    if not norm_query:
        return []

    raw_tokens = norm_query.split()
    keywords = [w for w in raw_tokens if w not in SEARCH_STOP_WORDS and len(w) > 1]
    if not keywords:
        keywords = [w for w in raw_tokens if len(w) > 1]
    if not keywords:
        return []

    conn = None
    try:
        init_db()
        conn = get_connection()
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()

    scored_results: list[tuple[float, dict[str, Any]]] = []

    for row in rows:
        title = row["title"] or ""
        norm_title = _normalize_text(title)
        if not norm_title:
            continue

        title_words = norm_title.split()
        score = 0.0

        if norm_query in norm_title:
            score += 10.0

        matched_keywords = 0
        for kw in keywords:
            kw_stem = _stem_ru(kw)
            best_word_score = 0.0

            if kw in norm_title:
                best_word_score = 3.0
            else:
                for tw in title_words:
                    tw_stem = _stem_ru(tw)
                    if len(kw_stem) >= 4 and (tw.startswith(kw_stem) or kw.startswith(tw_stem)):
                        best_word_score = max(best_word_score, 2.5)
                    elif len(kw) >= 4 and len(tw) >= 4:
                        ratio = SequenceMatcher(None, kw, tw).ratio()
                        if ratio >= 0.78:
                            best_word_score = max(best_word_score, ratio * 2.0)

            if best_word_score > 0:
                matched_keywords += 1
                score += best_word_score

        if matched_keywords > 0:
            if matched_keywords == len(keywords):
                score += 2.0
            scored_results.append((score, row_to_event_dict(row)))

    scored_results.sort(
        key=lambda item: (item[0], item[1].get("scheduled_at") or "", item[1]["id"]),
        reverse=True,
    )
    return [item[1] for item in scored_results[:limit]]


def execute_intent(intent: dict[str, Any]) -> dict[str, Any]:
    """Главная точка входа для app.py."""
    if not isinstance(intent, dict):
        return make_result(
            ok=False,
            message="Некорректный формат намерения (ожидался словарь).",
            error_code="validation_error",
        )

    action = intent.get("action")
    if action not in VALID_ACTIONS:
        return make_result(
            ok=False,
            message=f"Неизвестное действие: '{action}'.",
            error_code="validation_error",
        )

    if action == "clarify":
        missing = intent.get("missing_fields")
        if not isinstance(missing, list):
            missing = []
        return make_result(
            ok=False,
            message="Уточните, пожалуйста, недостающие детали запроса.",
            error_code=None,
            needs_clarification=True,
            missing_fields=missing,
        )

    if action == "create_task":
        kind = intent.get("kind") or "task"
        if kind not in ("task", "reminder"):
            return make_result(
                ok=False,
                message=f"Для create_task допустимы типы task или reminder (получено: '{kind}').",
                error_code="validation_error",
                missing_fields=["kind"],
            )
        return create_event(
            kind=kind,
            title=intent.get("title") or "",
            scheduled_at=intent.get("date_time"),
            due_date=intent.get("due_date"),
        )

    if action == "create_meeting":
        return create_event(
            kind="meeting",
            title=intent.get("title") or "",
            scheduled_at=intent.get("date_time"),
            due_date=None,
        )

    if action == "list_events":
        period_start = intent.get("period_start")
        period_end = intent.get("period_end")
        if not period_start or not period_end:
            return make_result(
                ok=False,
                message="Для просмотра расписания необходимо указать период.",
                error_code="validation_error",
                needs_clarification=True,
                missing_fields=["period_start", "period_end"],
            )
        if not is_valid_iso_datetime(period_start) or not is_valid_iso_datetime(period_end):
            return make_result(
                ok=False,
                message="Границы периода должны быть в формате ISO 8601.",
                error_code="validation_error",
                missing_fields=["period_start", "period_end"],
            )

        events = list_events(period_start, period_end)
        msg = f"Найдено событий: {len(events)}" if events else "На выбранный период событий нет."
        return make_result(ok=True, message=msg, events=events)

    if action == "search_events":
        query = intent.get("query")
        if not isinstance(query, str) or not query.strip():
            return make_result(
                ok=False,
                message="Укажите поисковый запрос.",
                error_code="validation_error",
                needs_clarification=True,
                missing_fields=["query"],
            )

        events = search_events(query)
        msg = f"Найдено записей: {len(events)}" if events else "По вашему запросу ничего не найдено."
        return make_result(ok=True, message=msg, events=events)

    return make_result(
        ok=False,
        message="Не удалось обработать команду.",
        error_code="validation_error",
    )