"""
שחזור קבצים מהאשפה של Windows לפי נתיב מקור (best-effort, מפרט §5).

send2trash אינו מחזיר handle לפריט באשפה — לכן שחזור אוטומטי מדויק
דורש חיפוש באשפה לפי שם/נתיב מקורי דרך ה-Windows Shell API (winshell).
זמין רק ב-Windows וכש-winshell מותקן; בכל מקרה אחר מוחזרת רשימה ריקה
במפורש, כדי שהמשתמש ידע בדיוק אילו קבצים דורשים שחזור ידני מהאשפה
ואילו שוחזרו אוטומטית בפועל — לא "בטוח שזה עבד".
"""

import platform
from pathlib import Path


def restore_from_recycle_bin(original_paths: list[str]) -> tuple[list[str], list[str]]:
    """
    מנסה לשחזר כל נתיב ברשימה. מחזיר (restored, failed) — שתי רשימות
    נפרדות, לעולם לא מדווח הצלחה שלא אומתה בפועל.
    """
    if platform.system() != "Windows":
        return [], list(original_paths)

    try:
        import winshell  # type: ignore
    except ImportError:
        return [], list(original_paths)

    restored, failed = [], []
    original_names = {Path(p).name: p for p in original_paths}

    try:
        for item in winshell.recycle_bin():
            original_filename = str(item.original_filename())
            name = Path(original_filename).name
            if name in original_names:
                try:
                    item.undelete()
                    restored.append(original_names[name])
                except Exception:  # noqa: BLE001
                    failed.append(original_names[name])
    except Exception:  # noqa: BLE001 — כשל בגישה לאשפה עצמה
        return [], list(original_paths)

    for p in original_paths:
        if p not in restored and p not in failed:
            failed.append(p)  # לא נמצא באשפה (כבר רוקנה ידנית וכו')

    return restored, failed
