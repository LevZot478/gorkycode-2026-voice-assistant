"""Speech recognition, loaded lazily to keep Streamlit startup lightweight."""
import os
import tempfile
from functools import lru_cache
from faster_whisper import WhisperModel

@lru_cache(maxsize=1)
def _model():
    return WhisperModel(os.getenv("WHISPER_MODEL_SIZE", "base"), device="cpu", compute_type="int8")

def transcribe_audio(audio_bytes: bytes) -> str:
    if not audio_bytes:
        raise ValueError("Аудиофайл пустой")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        segments, _ = _model().transcribe(path, language="ru", beam_size=3, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            raise ValueError("Не удалось распознать речь")
        return text
    finally:
        if path and os.path.exists(path):
            os.remove(path)
