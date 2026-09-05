import pytest

from core.memory.db import VertexMemory
from core.security.audit_log import AuditLog
from core.security.confirmation_gate import ConfirmationGate
from core.modules.file_ops import FileOpsModule


class AutoApproveWsManager:
    """מדמה משתמש שתמיד לוחץ 'אשר' — לבדיקת מסלול האושר בלבד."""
    def __init__(self, gate_ref_holder):
        self.gate_ref_holder = gate_ref_holder

    async def broadcast(self, payload):
        if payload["type"] == "CONFIRM_REQUIRED":
            self.gate_ref_holder["gate"].resolve(payload["task_id"], True)


@pytest.mark.asyncio
async def test_delete_matching_requires_approval_and_moves_to_trash(tmp_path, monkeypatch):
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()
    for i in range(3):
        (target_dir / f"file_{i}.tmp").write_text("data")

    holder = {}
    ws = AutoApproveWsManager(holder)
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(ws, audit)
    holder["gate"] = gate
    memory = VertexMemory(str(tmp_path / "memory.db"))

    trashed = []

    def fake_send2trash(path):
        trashed.append(path)

    import core.modules.file_ops as file_ops_module
    monkeypatch.setattr(file_ops_module, "send2trash", fake_send2trash)

    module = FileOpsModule(gate, memory, audit)
    result = await module.delete_matching(str(target_dir), "*.tmp")

    assert result.success is True
    assert len(trashed) == 3
    assert result.undo_id is not None


@pytest.mark.asyncio
async def test_no_deletion_without_approval(tmp_path):
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()
    (target_dir / "keep_me.tmp").write_text("data")

    holder = {}

    class AutoRejectWsManager:
        """מדמה משתמש שתמיד לוחץ 'בטל' — בלי להמתין ל-timeout של 300 שניות."""
        async def broadcast(self, payload):
            if payload["type"] == "CONFIRM_REQUIRED":
                holder["gate"].resolve(payload["task_id"], False)

    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(AutoRejectWsManager(), audit)
    holder["gate"] = gate
    memory = VertexMemory(str(tmp_path / "memory.db"))
    module = FileOpsModule(gate, memory, audit)

    result = await module.delete_matching(str(target_dir), "*.tmp")

    assert (target_dir / "keep_me.tmp").exists()  # לא נמחק
    assert result.success is False
