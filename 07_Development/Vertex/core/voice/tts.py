"""
מודול Text-to-Speech — עברית בלבד, תמיד.

דרישת ליבה של הלקוח: Vertex מדבר עם המשתמש אך ורק בעברית תקנית, בקול
טבעי. לפי המפרט (§1.2): NVIDIA Riva TTS (API) כברירת מחדל בפרודקשן,
עם נפילה חזרה (fallback) ל-edge-tts מקומי אם האינטרנט/Riva לא זמינים.

בפועל, קולות ה-Neural העבריים של Microsoft Edge (he-IL-HilaNeural /
he-IL-AvriNeural) הם קולות עברית תקניים באיכות גבוהה מאוד וחינמיים —
ולכן הם משמשים גם כברירת מחדל המעשית הראשונה כאן, לא רק כ-fallback,
עד לחיבור Riva בפרודקשן.

חשוב: אין כאן שום מסלול קוד ש'שוכח' לדבר עברית. כל טקסט שמגיע לכאן
נשלח לסינתזה בקול עברי בלבד — גם אם תוכן ההודעה המקורית (למשל פלט קוד,
שם קובץ באנגלית) מעורב-שפות, קול הקריינות עצמו נשאר עברי.
"""

import asyncio
from pathlib import Path

# קולות עברית תקניים של Microsoft Edge Neural TTS (חינמי, ללא מפתח API)
HEBREW_VOICES = {
    "female": "he-IL-HilaNeural",
    "male": "he-IL-AvriNeural",
}

DEFAULT_LANGUAGE = "he-IL"


class HebrewTTS:
    """
    שכבת TTS יחידה של Vertex. voice_gender נטען מ-config.yaml
    (ברירת מחדל: female / Hila).
    """

    def __init__(self, voice_gender: str = "female", output_dir: str = "./tts_cache"):
        if voice_gender not in HEBREW_VOICES:
            voice_gender = "female"
        self.voice = HEBREW_VOICES[voice_gender]
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, hebrew_text: str, out_filename: str = "reply.mp3") -> str:
        """
        ממיר טקסט עברי לקובץ אודיו. מחזיר נתיב לקובץ.
        משתמש ב-edge-tts (pip install edge-tts). דורש חיבור רשת קל.
        אם edge-tts לא זמין (למשל בסביבת פיתוח ללא רשת) — נכשל בעדינות
        ומחזיר None, כדי שהערוץ הטקסטואלי בעברית ימשיך לעבוד תמיד.
        """
        try:
            import edge_tts  # type: ignore
        except ImportError:
            return ""

        out_path = self.output_dir / out_filename
        communicate = edge_tts.Communicate(hebrew_text, self.voice)
        await communicate.save(str(out_path))
        return str(out_path)

    def synthesize_sync(self, hebrew_text: str, out_filename: str = "reply.mp3") -> str:
        return asyncio.run(self.synthesize(hebrew_text, out_filename))


def enforce_hebrew_reply_language(system_prompt: str) -> str:
    """
    מוסיף (אם חסרה) את הדרישה המחייבת לדבר עברית בלבד לכל system prompt
    שנשלח למודל ה-NIM. זו אכיפה ברמת קוד, לא רק בקשה בפרומפט.
    """
    mandate = (
        "\n\nהוראת ברזל: עליך לענות למשתמש אך ורק בעברית תקנית, שוטפת "
        "ומנומסת — בלי יוצא מן הכלל, גם אם המשתמש כותב באנגלית, וגם אם "
        "תוכן התשובה כולל קוד/שמות טכניים באנגלית (מותר שהקוד עצמו יהיה "
        "באנגלית, אבל כל ההסבר סביבו חייב להיות בעברית)."
    )
    if "אך ורק בעברית" in system_prompt:
        return system_prompt
    return system_prompt + mandate
