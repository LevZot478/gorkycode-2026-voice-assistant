import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_supabase_client = None


def is_test_mode() -> bool:
    """Если задан DATABASE_PATH (в тестах), используем SQLite."""
    return bool(os.getenv("DATABASE_PATH"))


def is_supabase_active() -> bool:
    """Supabase активен, если мы не в тестах и заданы ключи."""
    return not is_test_mode() and bool(SUPABASE_URL and SUPABASE_KEY)


def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL и SUPABASE_KEY не настроены")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH", "events.db")


def get_connection() -> sqlite3.Connection:
    """Возвращает соединение с SQLite (для тестов и локального режима)."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализирует таблицы в SQLite или проверяет Supabase."""
    if is_supabase_active():
        try:
            client = get_supabase_client()
            client.table("events").select("id").limit(1).execute()
            print("[Supabase] Подключение к облачной базе успешно.")
        except Exception as e:
            print(f"[Supabase] Ошибка подключения: {e}")
    else:
        conn = get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL DEFAULT 'task',
                        title TEXT NOT NULL,
                        scheduled_at TEXT,
                        due_date TEXT,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'open'
                    );
                    """
                )
        finally:
            conn.close()