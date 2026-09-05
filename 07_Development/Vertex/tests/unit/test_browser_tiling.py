import pytest

from core.modules.browser_automation import BrowserTaskManager, MAX_CONCURRENT_TASKS
from core.security.audit_log import AuditLog
from core.security.confirmation_gate import ConfirmationGate


class NoopWsManager:
    async def broadcast(self, payload):
        pass


@pytest.mark.asyncio
async def test_concurrent_tasks_get_distinct_slots(tmp_path):
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(NoopWsManager(), audit)
    manager = BrowserTaskManager(NoopWsManager(), gate)

    # מדמים משימות "רצות" בלי להריץ Playwright בפועל (בודקים רק את שכבת ה-slot allocation)
    for i in range(MAX_CONCURRENT_TASKS):
        task_id = f"task-{i}"
        from core.modules.browser_automation import BrowserTask
        manager.active_tasks[task_id] = BrowserTask(
            task_id=task_id, browser_choice="chromium", objective="x",
            slot_index=i, status="running",
        )

    with pytest.raises(RuntimeError):
        await manager.add_task("chromium", "משימה חמישית שאמורה להיחסם")


@pytest.mark.asyncio
async def test_next_free_slot_reuses_freed_slot(tmp_path):
    audit = AuditLog(str(tmp_path / "audit.db"))
    gate = ConfirmationGate(NoopWsManager(), audit)
    manager = BrowserTaskManager(NoopWsManager(), gate)

    from core.modules.browser_automation import BrowserTask
    manager.active_tasks["t0"] = BrowserTask(task_id="t0", browser_choice="chromium",
                                              objective="x", slot_index=0, status="done")
    manager.active_tasks["t1"] = BrowserTask(task_id="t1", browser_choice="chromium",
                                              objective="x", slot_index=1, status="running")

    assert manager._next_free_slot() == 0
