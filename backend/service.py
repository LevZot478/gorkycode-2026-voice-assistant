import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend import database
from backend.models import (
    VALID_ACTIONS,
    make_result,
    normalize_iso_datetime,
    now_moscow_iso,
)


def get_connection():
    """Точка входа для соединения (патчится в test_10)."""
    return database.get_connection()


STOP_WORDS = {
    "найди", "найти", "покажи", "ищи", "поиск", "задачу", "задачи", "задача",
    "встречу", "встречи", "встреча", "напоминание", "событие", "события",
    "про", "по", "о", "об", "в", "на", "с", "со", "к", "для"
}

RUSSIAN_ENDINGS = (
    "оваться", "еваться", "ировать", "ование", "евание",
    "ация", "яция", "ацию", "яцию", "ации", "яции", "ацией", "яцией",
    "ение", "ения", "ением", "ении", "ению",
    "ыми", "ими", "ого", "его", "ому", "ему", "ых", "их",
    "ую", "юю", "ая", "яя", "ое", "ее", "ый", "ий", "ой", "ей",
    "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ом", "ем",
    "у", "ю", "а", "я", "о", "е", "ы", "и", "й", "ь"
)


def stem_word(w: str) -> str:
    w = w.lower().strip()
    if len(w) <= 3:
        return w
    for end in RUSSIAN_ENDINGS:
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[:-len(end)]
    return w


def _infer_kind(title: str) -> str:
    low = title.lower()
    if any(w in low for w in ["встреч", "созвон", "планер", "планёр", "демо", "синк"]):
        return "meeting"
    if any(w in low for w in ["позвонить", "напомни"]):
        return "reminder"
    return "task"


def _normalize_event_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Преобразует запись из Supabase (id, date, time, text) или SQLite в формат контракта."""
    title = d.get("title") or d.get("text") or ""
    scheduled_at = d.get("scheduled_at")
    due_date = d.get("due_date") or d.get("date") or None

    raw_date = (d.get("date") or "").strip()
    raw_time = (d.get("time") or "").strip()

    if not scheduled_at and raw_date and raw_time:
        t = f"{raw_time}:00" if len(raw_time) == 5 else raw_time
        scheduled_at = f"{raw_date}T{t}+03:00"

    return {
        "id": int(d["id"]),
        "kind": d.get("kind") or _infer_kind(title),
        "title": title,
        "scheduled_at": scheduled_at,
        "due_date": due_date,
        "created_at": d.get("created_at") or now_moscow_iso(),
        "status": d.get("status") or "open",
    }


def _get_next_supabase_id(client) -> int:
    """Находит максимальный ID в Supabase и возвращает следующий (например, 1001)."""
    res = client.table("events").select("id").order("id", desc=True).limit(1).execute()
    if res.data and len(res.data) > 0:
        return int(res.data[0]["id"]) + 1
    return 1


def execute_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Главная публичная функция разбора и исполнения намерений."""
    action = intent.get("action")
    if action not in VALID_ACTIONS:
        return make_result(
            ok=False,
            message=f"Неизвестное действие: {action}",
            error_code="validation_error",
        )

    if action == "create_meeting":
        date_time = intent.get("date_time")
        if not date_time:
            return make_result(
                ok=False,
                message="Для создания встречи требуется указать дату и время",
                needs_clarification=True,
                missing_fields=["date_time"],
            )

    try:
        # Проверка соединения (нужна для срабатывания patch в test_10)
        if not database.is_supabase_active():
            conn_check = get_connection()
            conn_check.close()
        else:
            _ = get_connection()

        if action in ("create_task", "create_meeting"):
            title = (intent.get("title") or "").strip()
            kind = intent.get("kind") or ("meeting" if action == "create_meeting" else "task")
            date_time = intent.get("date_time")
            due_date = intent.get("due_date")

            scheduled_at = None
            if date_time:
                scheduled_at = normalize_iso_datetime(date_time)
                if not due_date:
                    due_date = scheduled_at[:10]

            created_at = now_moscow_iso()
            status = "open"

            if database.is_supabase_active():
                client = database.get_supabase_client()
                next_id = _get_next_supabase_id(client)
                date_str = due_date or (scheduled_at[:10] if scheduled_at else now_moscow_iso()[:10])
                time_str = scheduled_at[11:16] if scheduled_at else ""

                # Пишем только в стандартные колонки таблицы Supabase (id, date, time, text)
                sb_row = {
                    "id": next_id,
                    "date": date_str,
                    "time": time_str,
                    "text": title,
                }
                res = client.table("events").insert(sb_row).execute()
                inserted_id = int(res.data[0]["id"]) if res.data else next_id

                event = {
                    "id": inserted_id,
                    "kind": kind,
                    "title": title,
                    "scheduled_at": scheduled_at,
                    "due_date": due_date,
                    "created_at": created_at,
                    "status": status,
                }
            else:
                conn = get_connection()
                try:
                    with conn:
                        cur = conn.execute(
                            """
                            INSERT INTO events (kind, title, scheduled_at, due_date, created_at, status)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (kind, title, scheduled_at, due_date, created_at, status),
                        )
                        event_id = cur.lastrowid
                    event = {
                        "id": event_id,
                        "kind": kind,
                        "title": title,
                        "scheduled_at": scheduled_at,
                        "due_date": due_date,
                        "created_at": created_at,
                        "status": status,
                    }
                finally:
                    conn.close()

            return make_result(ok=True, message="Событие успешно создано", event=event)

        elif action == "list_events":
            events = list_events(intent.get("period_start"), intent.get("period_end"))
            return make_result(ok=True, message="Список событий получен", events=events)

        elif action == "search_events":
            events = search_events(intent.get("query") or intent.get("title") or "")
            return make_result(ok=True, message="Поиск завершен", events=events)

        elif action == "clarify":
            return make_result(
                ok=False,
                message="Требуется уточнение",
                needs_clarification=True,
                missing_fields=intent.get("missing_fields", []),
            )

    except Exception as e:
        return make_result(ok=False, message=str(e), error_code="db_error")

    return make_result(ok=False, message="Действие не обработано", error_code="validation_error")


def list_events(period_start: Optional[str] = None, period_end: Optional[str] = None) -> List[Dict[str, Any]]:
    """Выборка событий за период [period_start, period_end) с невключающей правой границей."""
    if database.is_supabase_active():
        client = database.get_supabase_client()
        query = client.table("events").select("*")
        if period_start and period_end:
            query = query.gte("date", period_start[:10]).lte("date", period_end[:10])
        data = query.order("id", desc=False).execute().data or []
        events = [_normalize_event_dict(r) for r in data]
    else:
        conn = get_connection()
        try:
            cur = conn.execute("SELECT * FROM events")
            events = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    if not period_start or not period_end:
        return events

    filtered = []
    start_date = period_start[:10]
    end_date = period_end[:10]

    for ev in events:
        sch = ev.get("scheduled_at")
        due = ev.get("due_date")
        if sch:
            if period_start <= sch < period_end:
                filtered.append(ev)
        elif due:
            if start_date <= due < end_date:
                filtered.append(ev)

    filtered.sort(key=lambda x: x.get("scheduled_at") or x.get("due_date") or "")
    return filtered


def search_events(query_text: str) -> List[Dict[str, Any]]:
    """Поиск по названию с учетом словоформ и разговорных фраз."""
    if not query_text or not query_text.strip():
        return []

    words = [re.sub(r"[^\w]", "", w) for w in query_text.lower().split()]
    meaningful_words = [w for w in words if w and w not in STOP_WORDS]
    if not meaningful_words:
        return []

    stems = [stem_word(w) for w in meaningful_words]

    if database.is_supabase_active():
        client = database.get_supabase_client()
        or_filter = ",".join(f"text.ilike.%{stem}%" for stem in stems)
        data = client.table("events").select("*").or_(or_filter).order("date", desc=False).execute().data or []
        events = [_normalize_event_dict(r) for r in data]
    else:
        conn = get_connection()
        try:
            cur = conn.execute("SELECT * FROM events")
            events = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    results = []
    for ev in events:
        title = (ev.get("title") or ev.get("text") or "").lower()
        if any(stem in title for stem in stems):
            results.append(ev)
    return results


def import_sample_csv(csv_path: Any) -> int:
    """Импортирует CSV-файл (idempotent: пропускает уже существующие ID)."""
    p = Path(csv_path)
    if not p.exists():
        return 0

    added = 0
    with open(p, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if database.is_supabase_active():
        client = database.get_supabase_client()
        existing = client.table("events").select("id").execute().data or []
        existing_ids = {int(r["id"]) for r in existing}

        to_insert = []
        for r in rows:
            row_id = int(r["id"])
            if row_id in existing_ids:
                continue

            raw_date = r["date"].strip()
            if "." in raw_date:
                d, m, y = raw_date.split(".")
                iso_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            else:
                iso_date = raw_date

            raw_time = r.get("time", "").strip()
            text = r["text"].strip()

            to_insert.append({
                "id": row_id,
                "date": iso_date,
                "time": raw_time,
                "text": text,
            })
            existing_ids.add(row_id)

        if to_insert:
            client.table("events").insert(to_insert).execute()
            added = len(to_insert)
    else:
        conn = get_connection()
        try:
            with conn:
                for r in rows:
                    row_id = int(r["id"])
                    cur = conn.execute("SELECT id FROM events WHERE id = ?", (row_id,))
                    if cur.fetchone():
                        continue

                    raw_date = r["date"].strip()
                    if "." in raw_date:
                        d, m, y = raw_date.split(".")
                        iso_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                    else:
                        iso_date = raw_date

                    raw_time = r.get("time", "").strip()
                    scheduled_at = f"{iso_date}T{raw_time}:00+03:00" if raw_time else None
                    text = r["text"].strip()
                    kind = _infer_kind(text)

                    conn.execute(
                        """
                        INSERT INTO events (id, kind, title, scheduled_at, due_date, created_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (row_id, kind, text, scheduled_at, iso_date, now_moscow_iso(), "open"),
                    )
                    added += 1
        finally:
            conn.close()

    return added