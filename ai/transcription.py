from faster_whisper import WhisperModel
import tempfile
import os


MODEL_SIZE = "small"

model = WhisperModel(
    MODEL_SIZE,
    device="cpu",
    compute_type="int8"
)


def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Преобразует аудио в текст на русском языке.
    """

    if not audio_bytes:
        raise ValueError("Аудиофайл пустой")

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        segments, info = model.transcribe(
            temp_path,
            language="ru",
            beam_size=3,
            vad_filter=True
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        if not text:
            raise ValueError("Не удалось распознать речь")

        return text

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)