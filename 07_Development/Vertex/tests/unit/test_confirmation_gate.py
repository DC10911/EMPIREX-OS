import asyncio

import pytest

from core.security.audit_log import AuditLog
from core.security.confirmation_gate import ConfirmationGate, RiskLevel


class FakeWsManager:
    def __init__(self):
        self.broadcasted = []

    async def broadcast(self, payload):
        self.broadcasted.append(payload)


@pytest.mark.asyncio
async def test_confirmation_approved(tmp_path):
    ws = FakeWsManager()
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(ws, audit)

    async def approver():
        await asyncio.sleep(0.05)
        task_id = ws.broadcasted[0]["task_id"]
        gate.resolve(task_id, True)

    asyncio.create_task(approver())
    approved = await gate.request("מחיקת קבצים", {"files": ["a.txt"]}, risk=RiskLevel.MEDIUM)
    assert approved is True
    assert ws.broadcasted[0]["type"] == "CONFIRM_REQUIRED"


@pytest.mark.asyncio
async def test_confirmation_timeout_defaults_to_reject(tmp_path):
    ws = FakeWsManager()
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(ws, audit)

    approved = await gate.request("פעולה מסוכנת", {}, timeout_sec=0.05)
    assert approved is False


@pytest.mark.asyncio
async def test_no_action_without_explicit_approval(tmp_path):
    """שום פעולה לא מתבצעת עד לחיצת 'אשר' — דחייה מפורשת חוסמת."""
    ws = FakeWsManager()
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(ws, audit)

    async def rejecter():
        await asyncio.sleep(0.05)
        task_id = ws.broadcasted[0]["task_id"]
        gate.resolve(task_id, False)

    asyncio.create_task(rejecter())
    approved = await gate.request("מחיקת קבצים", {"files": ["a.txt"]})
    assert approved is False
