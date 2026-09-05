"""
מודול Speech-to-Text — זיהוי דיבור בעברית (מפרט §2, §15.2).

משתמש ב-faster-whisper (מודל Whisper ממוטב) שרץ לוקאלית לגמרי, ללא
שליחת אודיו לרשת — פרטיות כברירת מחדל. language="he" נכפה תמיד, כך
שגם אם המשתמש מדבר במבטא/מילים לועזיות בתוך המשפט, המודל מפרש כעברית.
"""

from pathlib import Path

_model_cache = None


def _get_model(model_size: str = "small"):
    global _model_cache
    if _model_cache is None:
        from faster_whisper import WhisperModel  # type: ignore
        _model_cache = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache


def transcribe_hebrew(audio_path: str, model_size: str = "small") -> str:
    """מתמלל קובץ אודיו (WAV/MP3) לעברית. מחזיר טקסט בלבד."""
    if not Path(audio_path).exists():
        raise FileNotFoundError(audio_path)
    model = _get_model(model_size)
    segments, _info = model.transcribe(audio_path, language="he", vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()
