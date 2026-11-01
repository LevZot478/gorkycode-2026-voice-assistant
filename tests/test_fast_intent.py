"""Regression tests for fast common commands on free Codespaces CPU."""
import os
import unittest
from unittest.mock import patch

from ai.fast_intent import parse_fast_intent

NOW = "2026-11-01T19:04:00+03:00"


class FastIntentTests(unittest.TestCase):
    def test_meeting_tomorrow(self):
        r = parse_fast_intent("Добавь встречу завтра в 15:00", NOW)
        self.assertEqual(r["action"], "create_meeting")
        self.assertEqual(r["date_time"], "2026-11-02T15:00:00+03:00")
        self.assertEqual(r["title"], "Встреча")
        self.assertEqual(len(r), 9)

    def test_meeting_with_subject(self):
        r = parse_fast_intent("Добавь встречу с командой завтра в 15:00", NOW)
        self.assertEqual(r["title"], "Встреча с командой")

    def test_reminder_tomorrow(self):
        r = parse_fast_intent("Напомни завтра в 10 позвонить Ивану", NOW)
        self.assertEqual(r["action"], "create_task")
        self.assertEqual(r["kind"], "reminder")
        self.assertEqual(r["title"], "Позвонить Ивану")
        self.assertEqual(r["date_time"], "2026-11-02T10:00:00+03:00")

    def test_list_today(self):
        r = parse_fast_intent("Что у меня сегодня?", NOW)
        self.assertEqual(r["action"], "list_events")
        self.assertEqual(r["period_start"], "2026-11-01T00:00:00+03:00")
        self.assertEqual(r["period_end"], "2026-11-02T00:00:00+03:00")

    def test_list_this_week(self):
        r = parse_fast_intent("Что у меня на этой неделе?", NOW)
        self.assertEqual(r["period_start"], "2026-10-26T00:00:00+03:00")
        self.assertEqual(r["period_end"], "2026-11-02T00:00:00+03:00")

    def test_search_presentation(self):
        r = parse_fast_intent("Найди задачу про презентацию", NOW)
        self.assertEqual(r["action"], "search_events")
        self.assertEqual(r["query"], "презентацию")

    def test_meeting_without_time_clarifies(self):
        r = parse_fast_intent("Добавь встречу завтра", NOW)
        self.assertEqual(r["action"], "clarify")
        self.assertIn("время", r["missing_fields"])

    def test_task_only_date(self):
        r = parse_fast_intent("Создай задачу подготовить презентацию завтра", NOW)
        self.assertEqual(r["action"], "create_task")
        self.assertEqual(r["due_date"], "2026-11-02")
        self.assertIsNone(r["date_time"])

    def test_ambiguous_prompt_uses_llm(self):
        self.assertIsNone(parse_fast_intent("Хочу что-нибудь интересное", NOW))

    def test_fast_mode_never_calls_network(self):
        from ai.intent import parse_intent
        with patch.dict(os.environ, {"FAST_INTENT": "1"}):
            with patch("ai.intent.requests.post") as request:
                result = parse_intent("Напомни завтра в 10 позвонить Ивану", NOW)
                self.assertEqual(result["action"], "create_task")
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
