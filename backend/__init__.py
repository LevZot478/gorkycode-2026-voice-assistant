from backend.database import get_connection, init_db
from backend.service import (
    execute_intent,
    import_sample_csv,
    list_events,
    search_events,
)

# Инициализируем БД при старте
try:
    init_db()
except Exception:
    pass

__all__ = [
    "init_db",
    "get_connection",
    "execute_intent",
    "list_events",
    "search_events",
    "import_sample_csv",
]