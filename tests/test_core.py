import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import execute_intent, import_sample_csv, init_db, list_events, search_events


class BackendCoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_events.db")
        os.environ["DATABASE_PATH"] = self.db_path
        init_db()

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_PATH", None)
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_01_create_task_with_datetime(self) -> None:
        """1. create_task с date_time создает событие нужного типа и возвращает настоящий ID."""
        res = execute_intent({
            "action": "create_task",
            "title": "Позвонить Ивану",
            "date_time": "2026-10-31T10:00:00+03:00",
            "period_start": None,
            "period_end": None,
            "query": None,
            "missing_fields": [],
            "kind": "reminder",
            "due_date": None,
        })
        self.assertTrue(res["ok"])
        self.assertIsNotNone(res["event"])
        self.assertIsInstance(res["event"]["id"], int)
        self.assertEqual(res["event"]["kind"], "reminder")
        self.assertEqual(res["event"]["scheduled_at"], "2026-10-31T10:00:00+03:00")

    def test_02_create_meeting_without_time_fails(self) -> None:
        """2. create_meeting без времени не пишет запись и требует уточнения."""
        res = execute_intent({
            "action": "create_meeting",
            "title": "Встреча с Иваном",
            "date_time": None,
            "period_start": None,
            "period_end": None,
            "query": None,
            "missing_fields": [],
            "kind": "meeting",
            "due_date": None,
        })
        self.assertFalse(res["ok"])
        self.assertTrue(res["needs_clarification"])
        self.assertIn("date_time", res["missing_fields"])
        self.assertEqual(len(list_events("2026-01-01T00:00:00+03:00", "2027-01-01T00:00:00+03:00")), 0)

    def test_03_create_task_only_due_date(self) -> None:
        """3. create_task только с due_date сохраняет дату без фиктивного часа."""
        res = execute_intent({
            "action": "create_task",
            "title": "Отправить отчёт",
            "date_time": None,
            "period_start": None,
            "period_end": None,
            "query": None,
            "missing_fields": [],
            "kind": "task",
            "due_date": "2026-10-30",
        })
        self.assertTrue(res["ok"])
        self.assertIsNone(res["event"]["scheduled_at"])
        self.assertEqual(res["event"]["due_date"], "2026-10-30")

    def test_04_and_05_list_events_period_and_exclusive_end(self) -> None:
        """4-5. list_events за сегодня не возвращает завтрашние события и не включает правую границу."""
        execute_intent({
            "action": "create_meeting",
            "title": "Утренний синк",
            "date_time": "2026-10-30T11:00:00+03:00",
            "kind": "meeting",
        })
        execute_intent({
            "action": "create_meeting",
            "title": "Ровно полночь следующего дня",
            "date_time": "2026-10-31T00:00:00+03:00",
            "kind": "meeting",
        })

        today_events = list_events("2026-10-30T00:00:00+03:00", "2026-10-31T00:00:00+03:00")
        self.assertEqual(len(today_events), 1)
        self.assertEqual(today_events[0]["title"], "Утренний синк")

    def test_06_search_events_presentation(self) -> None:
        """6. search_events('презентация') находит подходящую запись в другой словоформе."""
        execute_intent({
            "action": "create_task",
            "title": "Подготовить презентацию для команды",
            "date_time": "2026-10-30T14:00:00+03:00",
            "kind": "task",
        })
        found = search_events("презентация")
        self.assertEqual(len(found), 1)
        self.assertIn("презентацию", found[0]["title"])

        found_natural = search_events("Найди задачу про презентацию")
        self.assertEqual(len(found_natural), 1)

    def test_07_empty_search_and_unknown_action(self) -> None:
        """7. Пустой поиск возвращает [], неизвестный action — ошибку."""
        self.assertEqual(search_events(""), [])
        self.assertEqual(search_events("космического хомяка"), [])

        bad_res = execute_intent({"action": "delete_everything"})
        self.assertFalse(bad_res["ok"])
        self.assertEqual(bad_res["error_code"], "validation_error")

    def test_08_persistence_across_connections(self) -> None:
        """8. После повторного открытия соединения новая запись сохраняется."""
        execute_intent({
            "action": "create_task",
            "title": "Купить билеты",
            "due_date": "2026-11-01",
            "kind": "task",
        })
        events = list_events("2026-11-01T00:00:00+03:00", "2026-11-02T00:00:00+03:00")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Купить билеты")

    def test_09_idempotent_csv_import(self) -> None:
        """9. Импорт CSV дважды не создает дубликатов."""
        csv_file = Path(self.temp_dir.name) / "sample.csv"
        csv_file.write_text(
            "id,date,time,text\n"
            "1,2026-10-30,10:00,Согласовать договор с клиентом\n"
            "2,31.10.2026,15:30,Подготовить презентацию проекта\n",
            encoding="utf-8",
        )
        added_first = import_sample_csv(csv_file)
        added_second = import_sample_csv(csv_file)

        self.assertEqual(added_first, 2)
        self.assertEqual(added_second, 0)
        self.assertEqual(len(search_events("договор")), 1)

    def test_10_db_error_returns_ok_false(self) -> None:
        """10. Ошибка БД не превращается в ok=True."""
        with patch("backend.service.get_connection", side_effect=RuntimeError("Disk full")):
            res = execute_intent({
                "action": "create_task",
                "title": "Тест падения БД",
                "kind": "task",
            })
            self.assertFalse(res["ok"])
            self.assertEqual(res["error_code"], "db_error")


if __name__ == "__main__":
    unittest.main()