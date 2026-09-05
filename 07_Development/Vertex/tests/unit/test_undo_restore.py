import pytest

from core.memory.db import VertexMemory
from core.security.audit_log import AuditLog
from core.security.confirmation_gate import ConfirmationGate
from core.modules.file_ops import FileOpsModule


class NoopWsManager:
    async def broadcast(self, payload):
        pass


@pytest.mark.asyncio
async def test_undo_last_reports_honest_failure_when_restore_unsupported(tmp_path, monkeypatch):
    """בסביבה שאינה Windows/ללא winshell — undo_last חייב לדווח בכנות שלא שוחזר, לא לשקר."""
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(NoopWsManager(), audit)
    memory = VertexMemory(str(tmp_path / "memory.db"))
    module = FileOpsModule(gate, memory, audit)

    memory.write_undo_log("delete", '{"files": ["/tmp/a.txt", "/tmp/b.txt"], "directory": "/tmp"}')

    import core.modules.file_ops as file_ops_module
    monkeypatch.setattr(file_ops_module, "restore_from_recycle_bin",
                         lambda paths: ([], list(paths)))

    result = await module.undo_last()

    assert result.success is False
    assert "לא נתמך" in result.message or "ידני" in result.message


@pytest.mark.asyncio
async def test_undo_last_reports_success_when_restore_works(tmp_path, monkeypatch):
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(NoopWsManager(), audit)
    memory = VertexMemory(str(tmp_path / "memory.db"))
    module = FileOpsModule(gate, memory, audit)

    memory.write_undo_log("delete", '{"files": ["/tmp/a.txt"], "directory": "/tmp"}')

    import core.modules.file_ops as file_ops_module
    monkeypatch.setattr(file_ops_module, "restore_from_recycle_bin",
                         lambda paths: (list(paths), []))

    result = await module.undo_last()

    assert result.success is True
    assert result.affected == ["/tmp/a.txt"]


@pytest.mark.asyncio
async def test_undo_with_no_history(tmp_path):
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(NoopWsManager(), audit)
    memory = VertexMemory(str(tmp_path / "memory.db"))
    module = FileOpsModule(gate, memory, audit)

    result = await module.undo_last()
    assert result.success is False
    assert "אין פעולה" in result.message
