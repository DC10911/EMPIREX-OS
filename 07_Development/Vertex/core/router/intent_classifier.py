"""
סיווג כוונות (Intent Router, מפרט §4.1).

מיישם ניתוב היברידי: מנסה זיהוי מהיר בכללים (מילות מפתח בעברית) לפני
פנייה ל-NIM, כדי לחסוך latency ועלות על משפטים ברורים ("תמחק",
"תפתח דפדפן"). כשאין זיהוי חד-משמעי — נופל ל-NIM (llama-3.3-70b) עם
system prompt שמכריח החזרת JSON תקני של הכוונה.
"""

import json
import re

INTENTS = ("file_ops", "browser", "code_gen", "security_audit", "ethovx_train", "memory", "chat")

_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"מחק|תמחק|העבר לאשפה|מחיקה"), "file_ops"),
    (re.compile(r"שנה שם|העבר|ארגן תיקי|סדר את התיקי"), "file_ops"),
    (re.compile(r"פתח דפדפן|תחפש|חפש ב(גוגל|רשת)|תדפדף"), "browser"),
    (re.compile(r"כתוב קוד|תכתוב סקריפט|תבנה לי (כלי|תוכנה|אתר)"), "code_gen"),
    (re.compile(r"בדוק (לי )?אבטחה|סריקת אבטחה|חולשות אבטחה"), "security_audit"),
    (re.compile(r"תשכח|מחק זיכרון|נקה זיכרון"), "memory"),
    (re.compile(r"אמן|אימון|תתאמן|ETHOVX"), "ethovx_train"),
]


def classify_rule_based(user_input: str) -> "str | None":
    for pattern, intent in _RULES:
        if pattern.search(user_input):
            return intent
    return None


INTENT_CLASSIFIER_SYSTEM_PROMPT = (
    "אתה מסווג כוונות עבור סוכן AI בשם Vertex. סווג את הודעת המשתמש "
    "לאחת מהקטגוריות הבאות בלבד: file_ops, browser, code_gen, "
    "security_audit, ethovx_train, memory, chat. "
    'החזר אך ורק JSON תקני בפורמט {"intent": "<one_of_the_above>"} '
    "ללא שום טקסט נוסף."
)


def classify_via_nim(user_input: str, nim_client, model: str) -> str:
    messages = [
        {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    response = nim_client.chat_completion(model=model, messages=messages)
    text = nim_client.extract_text(response)
    try:
        data = json.loads(text)
        intent = data.get("intent", "chat")
        return intent if intent in INTENTS else "chat"
    except (json.JSONDecodeError, AttributeError):
        return "chat"


def classify_intent(user_input: str, nim_client=None, model: str = "meta/llama-3.3-70b-instruct") -> str:
    rule_hit = classify_rule_based(user_input)
    if rule_hit:
        return rule_hit
    if nim_client is not None:
        return classify_via_nim(user_input, nim_client, model)
    return "chat"
