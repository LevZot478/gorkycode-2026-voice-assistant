from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    completed: bool = False


@dataclass
class Meeting:
    title: str
    time: str


class VoiceAssistant:
    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._meetings: list[Meeting] = []

    def process_command(self, command: str) -> str:
        normalized = command.strip()
        lowered = normalized.lower()

        if lowered.startswith("add task "):
            title = normalized[9:].strip()
            if not title:
                return "Task title cannot be empty."
            task = Task(id=len(self._tasks) + 1, title=title)
            self._tasks.append(task)
            return f"Task #{task.id} added: {task.title}"

        if lowered == "list tasks":
            if not self._tasks:
                return "No tasks found."
            lines = []
            for task in self._tasks:
                status = "done" if task.completed else "pending"
                lines.append(f"{task.id}. [{status}] {task.title}")
            return "\n".join(lines)

        if lowered.startswith("complete task "):
            raw_id = normalized[14:].strip()
            if not raw_id.isdigit():
                return "Task id must be a number."
            task_id = int(raw_id)
            if task_id < 1 or task_id > len(self._tasks):
                return f"Task #{task_id} not found."
            task = self._tasks[task_id - 1]
            task.completed = True
            return f"Task #{task.id} marked as done."

        if lowered.startswith("schedule meeting "):
            payload = normalized[17:].strip()
            title, separator, time = payload.rpartition(" at ")
            if not separator or not title.strip() or not time.strip():
                return "Use: schedule meeting <title> at <time>"
            meeting = Meeting(title=title.strip(), time=time.strip())
            self._meetings.append(meeting)
            return f"Meeting scheduled: {meeting.title} at {meeting.time}"

        if lowered == "list meetings":
            if not self._meetings:
                return "No meetings found."
            return "\n".join(
                f"{index}. {meeting.title} at {meeting.time}"
                for index, meeting in enumerate(self._meetings, start=1)
            )

        if lowered in {"help", "commands"}:
            return (
                "Commands: add task <title>, complete task <id>, list tasks, "
                "schedule meeting <title> at <time>, list meetings"
            )

        return "Sorry, I didn't understand that command."


def main() -> None:
    assistant = VoiceAssistant()
    print("Voice assistant ready. Type 'help' for commands or 'exit' to quit.")
    while True:
        command = input("> ").strip()
        if command.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not command:
            continue
        print(assistant.process_command(command))


if __name__ == "__main__":
    main()
