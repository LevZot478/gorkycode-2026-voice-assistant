"""GORKYCODE 2026 — Frontend (Streamlit), красивая версия.

Поток: текст/микрофон -> ai.transcribe_audio -> ai.parse_intent
-> backend.execute_intent -> ответ. Без модулей ai/backend работает MOCK.
Запуск: python -m streamlit run app.py
"""
import re
import os
import hashlib
from datetime import date, datetime, timedelta, timezone
from html import escape

import streamlit as st

try:
    from zoneinfo import ZoneInfo
    MSK = ZoneInfo("Europe/Moscow")
except Exception:
    MSK = timezone(timedelta(hours=3))

# ---------------------------------------------------------- MOCK (временно)
_MOCK_DB: list[dict] = []


def _mock_parse_intent(text, now_iso):
    t = text.lower()
    b = {"action": "clarify", "title": None, "date_time": None,
         "period_start": None, "period_end": None, "query": None,
         "missing_fields": [], "kind": None, "due_date": None}
    day0 = datetime.fromisoformat(now_iso).replace(
        hour=0, minute=0, second=0, microsecond=0)
    if "найд" in t or "когда" in t:
        return {**b, "action": "search_events", "query": t.split()[-1]}
    if any(w in t for w in ("что у меня", "какие", "покажи", "есть ли")):
        s = day0 + (timedelta(days=1) if "завтра" in t else timedelta())
        return {**b, "action": "list_events", "period_start": s.isoformat(),
                "period_end": (s + timedelta(days=1)).isoformat()}
    if "встреч" in t:
        d = "".join(c for c in t if c.isdigit())
        if not d:
            return {**b, "title": text, "missing_fields": ["date_time"]}
        dt = (day0 + timedelta(days=1)).replace(hour=int(d[:2]))
        return {**b, "action": "create_meeting", "title": text,
                "date_time": dt.isoformat(), "kind": "meeting"}
    return {**b, "action": "create_task", "title": text, "kind": "task",
            "due_date": (day0 + timedelta(days=1)).date().isoformat()}


def _mock_transcribe_audio(audio_bytes):
    return "Тест: голос не распознаётся, пока нет ai.transcribe_audio"


def _mock_execute_intent(intent):
    r = {"ok": True, "message": "", "event": None, "events": [],
         "error_code": None, "needs_clarification": False,
         "missing_fields": []}
    a = intent.get("action")
    if a in ("create_task", "create_meeting"):
        ev = {"id": len(_MOCK_DB) + 1, "kind": intent.get("kind"),
              "title": intent.get("title"),
              "scheduled_at": intent.get("date_time"),
              "due_date": intent.get("due_date")}
        _MOCK_DB.append(ev)
        return {**r, "message": "Тест: запись создана (MOCK)", "event": ev}
    if a == "list_events":
        return {**r, "message": "Тест: вот что нашёл (MOCK)",
                "events": list(_MOCK_DB)}
    if a == "search_events":
        q = (intent.get("query") or "").lower()
        return {**r, "message": "Тест: результат поиска (MOCK)",
                "events": [e for e in _MOCK_DB
                           if q in (e["title"] or "").lower()]}
    return {**r, "ok": False, "needs_clarification": True,
            "message": "На какое время поставить встречу?",
            "missing_fields": intent.get("missing_fields", [])}


def _mock_list_events(start, end):
    return list(_MOCK_DB)


USING_MOCK_AI = USING_MOCK_BACKEND = False
try:
    from ai import parse_intent, transcribe_audio
except ImportError:
    parse_intent, transcribe_audio = _mock_parse_intent, _mock_transcribe_audio
    USING_MOCK_AI = True
try:
    from backend import execute_intent, list_events
except ImportError:
    execute_intent, list_events = _mock_execute_intent, _mock_list_events
    USING_MOCK_BACKEND = True
USING_MOCK = USING_MOCK_AI or USING_MOCK_BACKEND

# ---------------------------------------------------------------- стили
CSS = """
<style>
.stApp{background:radial-gradient(1200px 600px at 10% -10%,#2a1f5c 0%,transparent 60%),
radial-gradient(900px 500px at 100% 0%,#0e3b4f 0%,transparent 55%),#0f1020;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:860px;padding-top:2rem;}
.hero{padding:1.4rem 1.6rem;border-radius:22px;margin-bottom:1rem;
background:linear-gradient(135deg,rgba(139,92,246,.28),rgba(34,211,238,.16));
border:1px solid rgba(255,255,255,.12);box-shadow:0 10px 40px rgba(0,0,0,.35);}
.hero h1{margin:0;font-size:2rem;font-weight:800;
background:linear-gradient(90deg,#c4b5fd,#67e8f9);-webkit-background-clip:text;
-webkit-text-fill-color:transparent;}
.hero p{margin:.35rem 0 .7rem;color:#b9b6d6;}
.pill{display:inline-block;padding:.15rem .7rem;border-radius:999px;font-size:.78rem;
font-weight:600;border:1px solid;}
.pill.ok{color:#6ee7b7;border-color:#10b98166;background:#10b98118;}
.pill.mock{color:#fcd34d;border-color:#f59e0b66;background:#f59e0b18;}
.ev{--c:#94a3b8;margin:.45rem 0;padding:.65rem .9rem;border-radius:14px;
background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);
border-left:5px solid var(--c);}
.ev-top{display:flex;justify-content:space-between;gap:.6rem;flex-wrap:wrap;}
.badge{color:var(--c);font-weight:700;font-size:.82rem;}
.when{color:#b9b6d6;font-size:.82rem;}
.ev-title{margin-top:.2rem;font-size:1rem;font-weight:600;color:#f3f1ff;}
.empty{text-align:center;padding:1.2rem;border-radius:18px;color:#b9b6d6;
border:1px dashed rgba(255,255,255,.2);background:rgba(255,255,255,.03);}
[data-testid="stChatMessage"]{background:rgba(255,255,255,.045);
border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:.8rem 1rem;}
div.stButton>button{border-radius:999px;border:1px solid rgba(255,255,255,.18);
background:rgba(255,255,255,.06);color:#eceaf7;transition:.15s;width:100%;}
div.stButton>button:hover{border-color:#8b5cf6;background:#8b5cf633;
transform:translateY(-1px);color:#fff;}
section[data-testid="stSidebar"]{background:#13142b;
border-right:1px solid rgba(255,255,255,.08);}
</style>
"""

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
KIND = {"task": ("✅", "Задача", "#34d399"),
        "reminder": ("⏰", "Напоминание", "#fbbf24"),
        "meeting": ("📅", "Встреча", "#818cf8")}
SUGGESTIONS = ["Что у меня сегодня?", "Добавь встречу завтра в 15:00",
               "Напомни завтра в 10 позвонить Ивану",
               "Найди задачу про презентацию"]


def format_when(ev):
    s, d = ev.get("scheduled_at"), ev.get("due_date")
    try:
        if s:
            dt = datetime.fromisoformat(s)
            return f"{dt.day} {MONTHS[dt.month - 1]}, {dt:%H:%M}"
        if d:
            x = date.fromisoformat(d)
            return f"{x.day} {MONTHS[x.month - 1]}"
    except ValueError:
        return str(s or d)
    return "без даты"


def event_card(ev):
    icon, label, color = KIND.get(ev.get("kind"), ("📌", "Запись", "#94a3b8"))
    return (f'<div class="ev" style="--c:{color}"><div class="ev-top">'
            f'<span class="badge">{icon} {label}</span>'
            f'<span class="when">🕒 {escape(format_when(ev))}</span></div>'
            f'<div class="ev-title">{escape(str(ev.get("title") or "—"))}'
            f'</div></div>')


def render_events(events, show_empty=False):
    if events:
        st.markdown("".join(event_card(e) for e in events),
                    unsafe_allow_html=True)
    elif show_empty:
        st.markdown('<div class="empty">🔍 Ничего не найдено</div>',
                    unsafe_allow_html=True)


def render_assistant(m):
    {"success": st.success, "warning": st.warning,
     "error": st.error}.get(m.get("level"), st.write)(m["content"])
    render_events(m.get("events", []), m.get("show_empty", False))


# ---------------------------------------------------------------- логика
def reply(level, content, **extra):
    st.session_state.messages.append(
        {"role": "assistant", "level": level, "content": content, **extra})

def parse_spoken_time(text):
    """Преобразует время, записанное словами, в формат HH:MM."""

    text = text.lower()

    # Варианты: «в половине пятого», «в половине третьего»
    half_hours = {
        "второго": 1,
        "третьего": 2,
        "четвертого": 3,
        "четвёртого": 3,
        "пятого": 4,
        "шестого": 5,
        "седьмого": 6,
        "восьмого": 7,
        "девятого": 8,
        "десятого": 9,
        "одиннадцатого": 10,
        "двенадцатого": 11
    }

    # Варианты: «в четверть шестого», «в четверть пятого»
    if "четверть" in text:
        quarter_hours = {
            "второго": 1,
            "третьего": 2,
            "четвертого": 3,
            "четвёртого": 3,
            "пятого": 4,
            "шестого": 5,
            "седьмого": 6,
            "восьмого": 7,
            "девятого": 8,
            "десятого": 9,
            "одиннадцатого": 10,
            "двенадцатого": 11
        }

        for word, hour in quarter_hours.items():
            if re.search(rf"\b{word}\b", text):
                if any(w in text for w in (
                    "дня", "днем", "днём", "вечера", "вечером"
                )):
                    hour += 12

                return f"{hour:02d}:15"
    if "половине" in text:
        for word, hour in half_hours.items():
            if re.search(rf"\b{word}\b", text):
                if "утра" in text or "утром" in text:
                    pass
                elif any(w in text for w in ("дня", "днем", "днём",
                                              "вечера", "вечером")):
                    hour += 12

                return f"{hour:02d}:30"

    numbers = {
        "один": 1, "одна": 1, "два": 2, "две": 2,
        "три": 3, "четыре": 4, "пять": 5,
        "шесть": 6, "семь": 7, "восемь": 8,
        "девять": 9, "десять": 10, "одиннадцать": 11,
        "двенадцать": 12
    }

    # Поддержка чисел, распознанных Whisper цифрами
    digit_match = re.search(r'\b(\d{1,2})\b', text)

    if digit_match:
        number = int(digit_match.group(1))
    else:
        number = None
        for word, value in numbers.items():
            if re.search(rf"\b{word}\b", text):
                number = value
                break

    if number is None:
        return None

    if "утра" in text or "утром" in text:
        hour = number % 12

    elif "дня" in text or "днем" in text or "днём" in text:
        hour = number % 12 + 12

    elif "вечера" in text or "вечером" in text:
        hour = number % 12 + 12

    elif "ночи" in text or "ночью" in text:
        hour = number % 12

    else:
        return None

    return f"{hour:02d}:00"

def handle_request(text, from_voice=False):
    """Один маршрут для текста и голоса: UI -> AI -> Backend -> UI."""
    st.session_state.messages.append(
        {"role": "user", "content": text, "voice": from_voice})

    now_iso = datetime.now(MSK).isoformat(timespec="seconds")

    # Если ожидаем уточнение времени встречи
    pending = st.session_state.pending_meeting

    if pending:
        time_match = re.search(
            r'\b(?:в\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)\b',
            text.lower()
        )

        spoken_time = parse_spoken_time(text)

        time_value = None

        if time_match:
            time_value = (
                f"{time_match.group(1)}:{time_match.group(2)}"
            )
        elif spoken_time:
            time_value = spoken_time

        if time_value:
            full_text = f"{pending['text']} в {time_value}"
            st.session_state.pending_meeting = None
            text = full_text

    try:
        intent = parse_intent(text, now_iso)
    except Exception as exc:
        return reply("error", f"Не удалось разобрать запрос: {exc}")

    try:
        res = execute_intent(intent)
    except Exception as exc:
        return reply("error", f"Ошибка при выполнении действия: {exc}")

    # Сохраняем встречу, если нужно уточнить время
    if (intent.get("action") in ("create_meeting", "clarify")
            and intent.get("kind") == "meeting"
            and intent.get("date_time") is None
            and any(str(x).lower() in ("время", "date_time", "time")
                    for x in intent.get("missing_fields", []))):
        st.session_state.pending_meeting = {"text": text}
    if res.get("needs_clarification"):
        level = "warning"
    elif not res.get("ok"):
        level = "error"
    else:
        level = "success"

    events = res.get("events") or (
        [res["event"]] if res.get("event") else []
    )

    reply(
        level,
        res.get("message") or "Готово",
        events=events,
        show_empty=level == "success"
        and intent.get("action") in ("list_events", "search_events")
    )

def transcribe_once(audio_file):
    data = audio_file.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h == st.session_state.last_audio_hash:
        return None
    st.session_state.last_audio_hash = h
    try:
        return (transcribe_audio(data) or "").strip()
    except Exception as exc:
        reply("error", f"Не удалось распознать речь: {exc}")
        return None


# ---------------------------------------------------------------- страница
st.set_page_config(page_title="Голосовой ассистент", page_icon="🎙️")
st.markdown(CSS, unsafe_allow_html=True)
for k, v in (
    ("messages", []),
    ("last_audio_hash", None),
    ("audio_key", 0),
    ("pending_meeting", None)
):
    st.session_state.setdefault(k, v)

_has_giga = any(os.getenv(k) for k in (
    "GIGACHAT_AUTH_KEY", "GIGACHAT_CREDENTIALS", "GIGACHAT_ACCESS_TOKEN"))
_has_groq = bool(os.getenv("GROQ_API_KEY"))
_is_cloud = os.getenv("APP_ENV", "").lower() in ("production", "cloud")
if USING_MOCK:
    pill = '<span class="pill mock">● DEMO / MOCK</span>'
elif _has_giga:
    pill = '<span class="pill ok">● Режим: GigaChat API</span>'
elif _has_groq:
    pill = '<span class="pill ok">● Режим: облачный AI</span>'
elif _is_cloud:
    pill = '<span class="pill mock">● AI не настроен</span>'
else:
    pill = '<span class="pill mock">● Режим: локальная Ollama</span>'
st.markdown(f'<div class="hero"><h1>🎙️ Голосовой ассистент</h1>'
            f'<p>Задачи, напоминания и встречи — говорите или пишите '
            f'как удобно.</p>{pill}</div>', unsafe_allow_html=True)
if USING_MOCK:
    st.warning("Модули " + ", ".join(
        n for n, f in (("ai", USING_MOCK_AI), ("backend", USING_MOCK_BACKEND))
        if f) + " не найдены — данные ненастоящие.")

if _is_cloud and not (_has_giga or _has_groq):
    st.warning("Для AI-команд добавьте секрет GIGACHAT_AUTH_KEY в настройках сервера.")
if _is_cloud and not (
    os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")
) and not os.getenv("DATABASE_PATH"):
    st.warning("Сейчас используется временная SQLite. Для хранения после перезапуска настройте Supabase или DATABASE_PATH на постоянном диске.")

# быстрые подсказки
queued = None
cols = st.columns(2)
for i, s in enumerate(SUGGESTIONS):
    if cols[i % 2].button(s, key=f"sug_{i}"):
        queued = s

# ввод: аудио в поле чата, иначе отдельный микрофон
native_audio = True
try:
    chat_value = st.chat_input("Напишите или запишите запрос…",
                               accept_audio=True)
except TypeError:
    native_audio = False
    chat_value = st.chat_input("Напишите запрос…")
audio_widget = None
if not native_audio:
    with st.expander("🎤 Записать голосом", expanded=True):
        audio_widget = st.audio_input(
            "Запись", key=f"audio_{st.session_state.audio_key}")

text, voice, rerun = queued, False, False
if text is None and chat_value:
    if isinstance(chat_value, str):
        text = chat_value
    else:
        text = (getattr(chat_value, "text", None) or "").strip() or None
        audio = getattr(chat_value, "audio", None)
        if text is None and audio is not None:
            with st.spinner("Распознаю речь…"):
                text = transcribe_once(audio)
            voice = True
            if not text:
                reply("warning", "Не удалось разобрать речь. Попробуйте ещё.")
elif text is None and audio_widget is not None:
    with st.spinner("Распознаю речь…"):
        text = transcribe_once(audio_widget)
    voice, rerun = True, text is not None

if text:
    with st.spinner("Думаю…"):
        handle_request(text, from_voice=voice)
if rerun:
    st.session_state.audio_key += 1
    st.rerun()

# история
if not st.session_state.messages:
    st.markdown('<div class="empty">👋 Нажмите на подсказку выше или '
                'напишите свой запрос внизу</div>', unsafe_allow_html=True)
for m in st.session_state.messages:
    with st.chat_message(m["role"],
                         avatar="🧑" if m["role"] == "user" else "🤖"):
        if m["role"] == "user":
            st.write(("🎤 " if m.get("voice") else "") + m["content"])
        else:
            render_assistant(m)

# боковая панель
with st.sidebar:
    st.markdown("## 📋 Мои события")
    st.caption("Ближайшие 7 дней")
    c1, c2 = st.columns(2)
    if c1.button("🔄 Обновить"):
        st.rerun()
    if c2.button("🧹 Чат"):
        st.session_state.messages = []
        st.rerun()
    try:
        start = datetime.now(MSK).replace(hour=0, minute=0, second=0,
                                          microsecond=0)
        upcoming = list_events(start.isoformat(),
                               (start + timedelta(days=7)).isoformat())
        render_events(upcoming, show_empty=True)
    except Exception as exc:
        st.error("Не удалось загрузить события. Проверьте настройки базы данных.")