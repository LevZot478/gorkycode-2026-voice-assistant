"""Fast, deterministic parser for the four GORKYCODE demo scenarios.

This intentionally covers simple high-confidence requests only.
Other free-form requests still go to the configured LLM.
"""
import re
from datetime import date, datetime, timedelta

_FIELDS = ("action", "title", "date_time", "period_start", "period_end",
           "query", "missing_fields", "kind", "due_date")

_WEEKDAYS = {
    "понедель": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресен": 6,
}

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)")
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_TIME_RE = re.compile(r"\b(?:в\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_HOUR_RE = re.compile(r"\bв\s+([01]?\d|2[0-3])(?:\s+час(?:а|ов)?)?(?=\s|$)")
_RELATIVE_DATE_RE = re.compile(r"\b(?:послезавтра|завтра|сегодня)\b")
_WEEKDAY_RE = re.compile(
    r"\b(?:в\s+)?(?:понедельник\w*|вторник\w*|сред\w*|четверг\w*|"
    r"пятниц\w*|суббот\w*|воскресен\w*)\b"
)


def _intent(action, **kwargs):
    data = dict.fromkeys(_FIELDS)
    data["action"] = action
    data["missing_fields"] = []
    data.update(kwargs)
    return data


def _target_day(text, now):
    """Return (date, substring-to-remove) or (None, None)."""
    low = text.lower().replace("после завтра", "послезавтра")
    match = _ISO_DATE_RE.search(low)
    if match:
        try:
            value = date(*(int(x) for x in match.groups()))
            return value, match.group(0)
        except ValueError:
            return None, None

    match = _DATE_RE.search(low)
    if match:
        try:
            d, m, y = (int(x) for x in match.groups())
            return date(y, m, d), match.group(0)
        except ValueError:
            return None, None

    match = _RELATIVE_DATE_RE.search(low)
    if match:
        days = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[match.group(0)]
        return now.date() + timedelta(days=days), match.group(0)

    match = _WEEKDAY_RE.search(low)
    if match:
        weekday_text = match.group(0).removeprefix("в ").strip()
        for prefix, target in _WEEKDAYS.items():
            if weekday_text.startswith(prefix):
                offset = (target - now.weekday()) % 7
                if "следующ" in low and offset == 0:
                    offset = 7
                return now.date() + timedelta(days=offset), match.group(0)
    return None, None


def _time(text):
    """Return (hour, minute, matched substring) or (None, None, None)."""
    # Remove explicit dates so e.g. 2026-11-02 is never mistaken for a time.
    without_dates = _ISO_DATE_RE.sub(" ", _DATE_RE.sub(" ", text.lower()))
    match = _TIME_RE.search(without_dates)
    if match:
        return int(match.group(1)), int(match.group(2)), match.group(0)
    match = _HOUR_RE.search(without_dates)
    if match:
        return int(match.group(1)), 0, match.group(0)
    return None, None, None


def _clean_title(text, command_regex, date_token, time_token):
    title = re.sub(command_regex, "", text, count=1, flags=re.IGNORECASE)
    if date_token:
        title = re.sub(re.escape(date_token), " ", title, count=1, flags=re.IGNORECASE)
    if time_token:
        title = re.sub(re.escape(time_token), " ", title, count=1, flags=re.IGNORECASE)
    title = re.sub(r"\b(?:на\s+)?(?:следующей?|текущей?)\s+неделе\b",
                   " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" ,.:;—–-")
    return title[0].upper() + title[1:] if title else ""


def _day_period(now, offset=0):
    day = now.date() + timedelta(days=offset)
    begin = datetime.combine(day, datetime.min.time(), now.tzinfo)
    return begin.isoformat(), (begin + timedelta(days=1)).isoformat()


def _week_period(now, next_week=False):
    start_day = now.date() - timedelta(days=now.weekday())
    if next_week:
        start_day += timedelta(days=7)
    begin = datetime.combine(start_day, datetime.min.time(), now.tzinfo)
    return begin.isoformat(), (begin + timedelta(days=7)).isoformat()


def parse_fast_intent(text: str, now_iso: str):
    """Return an intent dict for clear commands, or None to invoke the LLM."""
    if not text or len(text) > 500:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    low = text.lower().replace("после завтра", "послезавтра")
    now = datetime.fromisoformat(now_iso)

    # Search comes before list so "найди встречу" isn't mistaken for a list.
    match = re.match(r"^(?:найди|найти|поищи|отыщи|ищи)\b\s*", low)
    if match:
        query = re.sub(
            r"^(?:(?:мне|пожалуйста|старую|старый|старое|задачу|задачи|"
            r"встречу|встречи|запись|событие|напоминание|про|о|об)\s+)+",
            "", text[match.end():], flags=re.IGNORECASE,
        ).strip(" ?!.,")
        if query:
            return _intent("search_events", query=query)
        return None

    is_list = bool(re.match(
        r"^(?:что у меня|какие (?:у меня )?(?:дела|задачи|встречи|планы)|"
        r"покажи (?:мне )?(?:расписание|все|задачи|встречи|планы)|"
        r"расписание|список (?:задач|встреч|событий))\b", low,
    ))
    if is_list:
        if "на следующей неделе" in low or "на будущей неделе" in low:
            start, end = _week_period(now, True)
        elif "на этой неделе" in low or "на неделе" in low:
            start, end = _week_period(now)
        elif "послезавтра" in low:
            start, end = _day_period(now, 2)
        elif "завтра" in low:
            start, end = _day_period(now, 1)
        elif "сегодня" in low:
            start, end = _day_period(now)
        else:
            return None
        return _intent("list_events", period_start=start, period_end=end)

    meeting_command = (
        r"^(?:(?:добавь|создай|запиши|назначь|поставь|запланируй)\s+"
        r"(?:мне\s+)?|)(?:встречу|встреча|созвон|совещание)\b"
    )
    reminder_command = r"^(?:напомни|напомнить|создай напоминание|добавь напоминание)\b"
    task_command = (
        r"^(?:(?:добавь|создай|запиши|поставь|запланируй)\s+"
        r"(?:мне\s+)?(?:задачу|дело)|(?:мне\s+)?(?:нужно|надо))\b"
    )
    if re.match(meeting_command, low):
        kind, action, command = "meeting", "create_meeting", meeting_command
    elif re.match(reminder_command, low):
        kind, action, command = "reminder", "create_task", reminder_command
    elif re.match(task_command, low):
        kind, action, command = "task", "create_task", task_command
    else:
        return None

    day, day_token = _target_day(low, now)
    hour, minute, time_token = _time(low)
    title = _clean_title(text, command, day_token, time_token)

    if kind == "meeting" and (day is None or hour is None):
        missing = []
        if day is None:
            missing.append("дата")
        if hour is None:
            missing.append("время")
        return _intent("clarify", title=title or "Встреча",
                       kind="meeting", missing_fields=missing)
    if kind == "meeting" and not title:
        title = "Встреча"
    if kind != "meeting" and not title:
        return None
    if hour is not None and day is None:
        # Do not invent the date for a time-only reminder/task.
        return None

    timestamp = None
    due_date = None
    if day is not None and hour is not None:
        timestamp = datetime(
            day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo
        ).isoformat()
    elif day is not None:
        due_date = day.isoformat()

    return _intent(action, title=title, kind=kind,
                   date_time=timestamp, due_date=due_date)
