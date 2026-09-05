"""
מודול ניהול קבצים (מפרט §5).

עיקרון: מחיקה = אשפה (send2trash), לא מחיקה קשיחה, כברירת מחדל — לעולם.
כל פעולה הרסנית עוברת confirmation_gate. כל פעולה נכתבת ל-Undo Log
ייעודי (JSON) כך שניתן לבטל אצווה שלמה בפקודה "וורטקס בטל את הפעולה
האחרונה". "מחיקה קשיחה" (shred) היא פעולה נפרדת ומפורשת בלבד — אינה
מיושמת כאן בברירת מחדל, ר' §3.2 ו-§Scope.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from core.security.confirmation_gate import ConfirmationGate, RiskLevel
from core.memory.db import VertexMemory

try:
    from send2trash import send2trash  # type: ignore
except ImportError:
    send2trash = None  # מותקן רק בסביבת Windows/פרודקשן בפועל


@dataclass
class FileOpsResult:
    success: bool
    message: str
    affected: list[str] = field(default_factory=list)
    undo_id: "str | None" = None


class FileOpsModule:
    def __init__(self, confirmation_gate: ConfirmationGate, memory: VertexMemory,
                 audit_log=None):
        self.gate = confirmation_gate
        self.memory = memory
        self.audit_log = audit_log

    async def delete_matching(self, directory: str, pattern: str,
                               source_untrusted: bool = False) -> FileOpsResult:
        """
        מוחק (=מעביר לאשפה) קבצים התואמים pattern (glob) בתיקייה נתונה.
        חייב אישור מפורש — תמיד (§4.1: 'מחיקה/העברה/שינוי שם — כן, תמיד').
        """
        base = Path(directory).expanduser()
        if not base.exists() or not base.is_dir():
            return FileOpsResult(False, f"התיקייה '{directory}' לא נמצאה.")

        matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
        if not matches:
            return FileOpsResult(True, f"לא נמצאו קבצים התואמים ל-'{pattern}' בתיקייה '{directory}'.")

        total_size_mb = round(sum(os.path.getsize(m) for m in matches) / (1024 * 1024), 2)
        approved = await self.gate.request(
            action_desc=f"מחיקת {len(matches)} קבצים ({total_size_mb}MB) לאשפה",
            details={"files": matches, "total_size_mb": total_size_mb, "directory": directory,
                     "pattern": pattern},
            risk=RiskLevel.MEDIUM,
            source_untrusted=source_untrusted,
        )
        if not approved:
            return FileOpsResult(False, "המחיקה בוטלה — לא התקבל אישור.")

        if send2trash is None:
            return FileOpsResult(False, "send2trash אינו מותקן בסביבה זו — לא בוצעה מחיקה.")

        deleted = []
        for f in matches:
            try:
                send2trash(f)
                deleted.append(f)
            except Exception as exc:  # noqa: BLE001 — ממשיך ליתר הקבצים (§28, VX-FILE-01)
                if self.audit_log:
                    self.audit_log.write("FILE_DELETE_ERROR", file=f, error=str(exc))

        undo_id = self.memory.write_undo_log(
            "delete", json.dumps({"files": deleted, "directory": directory}, ensure_ascii=False)
        )
        self.memory.log_task("file_ops", f"מחיקת {pattern} מתוך {directory}", "done",
                              f"{len(deleted)} קבצים הועברו לאשפה")
        if self.audit_log:
            self.audit_log.write("FILES_DELETED", count=len(deleted), directory=directory)

        return FileOpsResult(
            True,
            f"הועברו {len(deleted)} קבצים לאשפה. שחזור אפשרי מהאשפה עד לריקון ידני.",
            affected=deleted,
            undo_id=undo_id,
        )

    async def undo_last(self) -> FileOpsResult:
        """'וורטקס בטל את הפעולה האחרונה' — משחזר מהאשפה (best-effort)."""
        last = self.memory.get_last_undo()
        if not last:
            return FileOpsResult(False, "אין פעולה קודמת לביטול.")

        if last["action_type"] == "delete":
            # שחזור אמיתי מהאשפה תלוי OS (Windows Shell API); כאן מסמנים
            # את הרשומה כמבוטלת ומדווחים למשתמש להיכן לפנות ידנית אם
            # השחזור האוטומטי לא נתמך בסביבה הנוכחית.
            self.memory.mark_undo_reverted(last["id"])
            return FileOpsResult(True, "הפעולה סומנה כמבוטלת. שחזר את הקבצים מהאשפה של Windows.")

        return FileOpsResult(False, "סוג הפעולה האחרונה אינו נתמך לביטול אוטומטי.")
