import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.models import MOSCOW_TZ, now_moscow_iso

DEFAULT_DB_PATH = "events.db"


def get_db_path() -> str:
    """Возвращает путь к файлу БД из переменной окружения DATABASE_PATH."""
    return os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)


def get_connection() -> sqlite3.Connection:
    """Создает соединение с SQLite и включает доступ к полям по именам."""
    db_path = get_db_path()
    parent_dir = Path(db_path).parent
    if str(parent_dir) and str(parent_dir) != ".":
        parent_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Инициализирует таблицу events и индексы при первом запуске."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('task', 'reminder', 'meeting')),
        title TEXT NOT NULL CHECK(length(trim(title)) > 0),
        scheduled_at TEXT NULL,
        due_date TEXT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'done')),
        import_source TEXT NULL,
        import_source_id TEXT NULL,
        UNIQUE(import_source, import_source_id)
    );
    """
    create_idx_sched = "CREATE INDEX IF NOT EXISTS idx_events_scheduled_at ON events(scheduled_at);"
    create_idx_due = "CREATE INDEX IF NOT EXISTS idx_events_due_date ON events(due_date);"

    conn = get_connection()
    try:
        with conn:
            conn.execute(create_table_sql)
            conn.execute(create_idx_sched)
            conn.execute(create_idx_due)
    finally:
        conn.close()


def _parse_csv_datetime(date_str: str, time_str: str) -> str:
    """Конвертирует пару (date, time) из CSV в ISO 8601 (+03:00)."""
    d_clean = date_str.strip()
    t_clean = time_str.strip()

    parsed_date = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed_date = datetime.strptime(d_clean, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        raise ValueError(f"Неизвестный формат даты в CSV: {d_clean}")

    parsed_time = None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed_time = datetime.strptime(t_clean, fmt).time()
            break
        except ValueError:
            continue
    if parsed_time is None:
        raise ValueError(f"Неизвестный формат времени в CSV: {t_clean}")

    dt = datetime.combine(parsed_date, parsed_time, tzinfo=MOSCOW_TZ)
    return dt.isoformat(timespec="seconds")


def import_sample_csv(path: str | Path = "data/sample_events.csv") -> int:
    """
    Импортирует записи из CSV в таблицу events.
    Повторный запуск не создает дубликатов благодаря UNIQUE(import_source, import_source_id).
    """
    init_db()
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV-файл не найден: {csv_path}")

    created_at = now_moscow_iso()
    rows_to_insert = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = (row.get("id") or "").strip()
            raw_date = (row.get("date") or "").strip()
            raw_time = (row.get("time") or "").strip()
            raw_text = (row.get("text") or "").strip()

            if not raw_id or not raw_text or not raw_date or not raw_time:
                continue

            scheduled_at = _parse_csv_datetime(raw_date, raw_time)
            rows_to_insert.append(
                (
                    "task",
                    raw_text,
                    scheduled_at,
                    None,
                    created_at,
                    "open",
                    "sample_csv",
                    raw_id,
                )
            )

    insert_sql = """
    INSERT OR IGNORE INTO events (
        kind, title, scheduled_at, due_date, created_at, status, import_source, import_source_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn = get_connection()
    try:
        before_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        with conn:
            conn.executemany(insert_sql, rows_to_insert)
        after_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return after_count - before_count
    finally:
        conn.close()