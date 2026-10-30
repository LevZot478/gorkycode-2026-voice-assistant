import unittest

from voice_assistant import VoiceAssistant


class VoiceAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = VoiceAssistant()

    def test_add_and_list_tasks(self) -> None:
        added = self.assistant.process_command("add task Prepare sprint report")
        self.assertEqual(added, "Task #1 added: Prepare sprint report")
        listed = self.assistant.process_command("list tasks")
        self.assertEqual(listed, "1. [pending] Prepare sprint report")

    def test_complete_task(self) -> None:
        self.assistant.process_command("add task Draft meeting agenda")
        completed = self.assistant.process_command("complete task 1")
        self.assertEqual(completed, "Task #1 marked as done.")
        listed = self.assistant.process_command("list tasks")
        self.assertEqual(listed, "1. [done] Draft meeting agenda")

    def test_schedule_and_list_meetings(self) -> None:
        scheduled = self.assistant.process_command(
            "schedule meeting Team sync at 10:30"
        )
        self.assertEqual(scheduled, "Meeting scheduled: Team sync at 10:30")
        listed = self.assistant.process_command("list meetings")
        self.assertEqual(listed, "1. Team sync at 10:30")

    def test_invalid_commands(self) -> None:
        self.assertEqual(
            self.assistant.process_command("schedule meeting Wrong format"),
            "Use: schedule meeting <title> at <time>",
        )
        self.assertEqual(
            self.assistant.process_command("complete task abc"),
            "Task id must be a number.",
        )


if __name__ == "__main__":
    unittest.main()
