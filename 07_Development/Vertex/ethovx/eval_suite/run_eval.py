"""
מריץ סט שאלות בדיקה קבוע מול מודל ETHOVX (דרך Ollama) ומודד דיוק אמיתי
לפני/אחרי כל ריצת אימון (מפרט §9.1 שלב 4).

זהו ה"אחוזי התמחות" האמיתי שהמפרט דרש: לא מספר שרירותי, אלא eval מוגדר
מראש (questions.json) שהמשתמש יכול לבדוק בעצמו — שקוף ובר-אימות.
"""

import json
from dataclasses import dataclass
from pathlib import Path

QUESTIONS_PATH = Path(__file__).parent / "questions.json"


@dataclass
class EvalResult:
    total: int
    correct: int
    accuracy_pct: float
    failing_examples: list[dict]


def _keyword_match_score(answer: str, expected_keywords: list[str]) -> bool:
    """
    קריטריון פשוט ובר-שחזור: התשובה נחשבת נכונה אם היא מכילה לפחות
    מחצית ממילות המפתח הצפויות. אינו תלוי ב-LLM שיפוטי חיצוני (§9.1).
    """
    lowered = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in lowered)
    return hits >= max(1, len(expected_keywords) // 2)


def run_eval(query_fn) -> EvalResult:
    """
    query_fn: פונקציה sync/async-wrapped שמקבלת שאלה (str) ומחזירה
    תשובת מודל (str). מוזרקת כדי שהעברת המודל (Ollama/ETHOVX) לא
    תיהיה תלות קשיחה של קובץ ה-eval עצמו.
    """
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    correct = 0
    failing = []
    for q in questions:
        answer = query_fn(q["question"])
        if _keyword_match_score(answer, q["expected_keywords"]):
            correct += 1
        else:
            failing.append({"id": q["id"], "question": q["question"], "answer": answer})

    total = len(questions)
    accuracy = round(100 * correct / total, 1) if total else 0.0
    return EvalResult(total=total, correct=correct, accuracy_pct=accuracy, failing_examples=failing)
