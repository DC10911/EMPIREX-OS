"""
Confirmation Gate — שער האישור המרכזי של Vertex.

עיקרון ברזל (מפרט §4.3, §22.1): כל פעולה הרסנית (מחיקה/דריסת קובץ/הרצת קוד/
שליחת טופס עם פרטים אישיים) עוברת כאן. שום פעולה לא מתבצעת עד שהמשתמש
לוחץ במפורש 'אשר' בממשק. Timeout = דחייה (ברירת מחדל בטוחה), לא אישור.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfirmationTimeout(Exception):
    pass


class ConfirmationGate:
    """
    מנוהל ע"י ה-Orchestrator. כל מודול (file_ops, browser_automation,
    code_gen) מקבל רפרנס יחיד למופע הזה ולעולם לא עוקף אותו.
    """

    def __init__(self, ws_manager, audit_log):
        self.ws_manager = ws_manager
        self.audit_log = audit_log
        self._pending: dict[str, "asyncio.Future[bool]"] = {}

    async def request(
        self,
        action_desc: str,
        details: dict,
        risk: RiskLevel = RiskLevel.MEDIUM,
        source_untrusted: bool = False,
        timeout_sec: int = 300,
    ) -> bool:
        """שולח בקשת אישור ל-UI וממתין לתגובת המשתמש (או timeout=דחייה)."""
        task_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: "asyncio.Future[bool]" = loop.create_future()
        self._pending[task_id] = future

        payload = {
            "type": "CONFIRM_REQUIRED",
            "task_id": task_id,
            "action_desc": action_desc,
            "details": details,
            "risk_level": risk.value,
            # דגל אדום: אם הבקשה מקורה בתוכן חיצוני (דף אינטרנט/קובץ) ולא בבקשה
            # ישירה שלך — ר' injection_guard.py
            "flagged_external_source": source_untrusted,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.ws_manager.broadcast(payload)
        self.audit_log.write("CONFIRMATION_REQUESTED", task_id=task_id, **_safe(details))

        try:
            approved = await asyncio.wait_for(future, timeout=timeout_sec)
        except asyncio.TimeoutError:
            self.audit_log.write("CONFIRMATION_TIMEOUT", task_id=task_id)
            self._pending.pop(task_id, None)
            return False

        self.audit_log.write("CONFIRMATION_RESOLVED", task_id=task_id, approved=approved)
        self._pending.pop(task_id, None)
        return approved

    def resolve(self, task_id: str, approved: bool) -> bool:
        """נקרא מה-WebSocket handler כשמגיעה תגובת המשתמש בפועל (CONFIRM_RESOLVE)."""
        future = self._pending.get(task_id)
        if future and not future.done():
            future.set_result(approved)
            return True
        return False

    def pending_count(self) -> int:
        return len(self._pending)


def _safe(details: dict) -> dict:
    """לא כותב תוכן קבצים גולמי/סודות ללוג — רק metadata (ר' §24.1)."""
    out = {}
    for k, v in details.items():
        if k in ("api_key", "password", "raw_content"):
            continue
        out[k] = v
    return out
