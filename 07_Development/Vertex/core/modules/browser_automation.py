"""
מודול אוטומציית דפדפן — Phase 2 (מפרט §6, §18.3).

כל משימת דפדפן מקבלת BrowserContext נפרד של Playwright (לא רק טאב) —
מבודד עם session/cookies/state משלו, כך ששתי משימות לא 'מתנגשות' גם אם
זה אותו סוג דפדפן. פועל בחלון גלוי (headless=False) — לא הזרקה גולמית
לעכבר של Windows. תוכן דף = נתון בלבד, לעולם לא הרשאה (ר' injection_guard).

זהו שלד Phase 2 מלא מבחינת ממשק/ארכיטקטורה; להרצה בפועל יש להתקין
`playwright install` על סביבת Windows היעד.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field

from core.security.confirmation_gate import ConfirmationGate, RiskLevel
from core.security.injection_guard import ContentSource, detect_injection_attempt

# מגבלת NFR (§20): עד 4 משימות דפדפן מקביליות ללא ירידת ביצועים מורגשת.
MAX_CONCURRENT_TASKS = 4

# רשת tiling אוטומטית: עד 4 חלונות מסודרים ברביע נפרד של המסך, כדי
# שתוכל לראות את כולם בו-זמנית (§6.1) — מבוסס רזולוציית 1920x1080
# כברירת מחדל; בפרודקשן ניתן לזהות רזולוציה אמיתית דרך screeninfo.
_SCREEN_W, _SCREEN_H = 1920, 1080
_TILE_POSITIONS = [
    (0, 0), (_SCREEN_W // 2, 0),
    (0, _SCREEN_H // 2), (_SCREEN_W // 2, _SCREEN_H // 2),
]
_TILE_SIZE = (_SCREEN_W // 2, _SCREEN_H // 2)


@dataclass
class BrowserTask:
    task_id: str
    browser_choice: str          # chrome / edge / firefox
    objective: str
    slot_index: int = 0
    status: str = "pending"
    steps_log: list = field(default_factory=list)


class BrowserTaskManager:
    """
    מנהל ריבוי משימות דפדפן מקביליות. כל משימה חדשה נפתחת **לצד** הקודמות,
    לא מחליפה אותן — בדיוק לפי §3.3 (טאב 1 + טאב 2 רצים במקביל, כל אחת
    בפאנל צד עם סטטוס נפרד, ובסיום כל אחת — כרטיס דוח מסכם נפרד). חלונות
    מסודרים אוטומטית זה-לצד-זה על המסך (tiling, §6.1) לפי slot_index פנוי.
    """

    def __init__(self, ws_manager, gate: ConfirmationGate, nim_client=None):
        self.ws_manager = ws_manager
        self.gate = gate
        self.nim_client = nim_client
        self.active_tasks: dict[str, BrowserTask] = {}
        self._playwright = None

    def _next_free_slot(self) -> int:
        used = {t.slot_index for t in self.active_tasks.values() if t.status == "running"}
        for i in range(len(_TILE_POSITIONS)):
            if i not in used:
                return i
        return 0  # כל הסלוטים תפוסים — חופפים ל-slot הראשון (מעל המגבלה)

    async def add_task(self, browser_choice: str, objective: str) -> str:
        running = sum(1 for t in self.active_tasks.values() if t.status == "running")
        if running >= MAX_CONCURRENT_TASKS:
            raise RuntimeError(
                f"כבר רצות {MAX_CONCURRENT_TASKS} משימות דפדפן במקביל — המגבלה "
                "המומלצת לביצועים יציבים (§20 NFR). המתן לסיום משימה קיימת."
            )
        task = BrowserTask(task_id=str(uuid.uuid4()), browser_choice=browser_choice,
                            objective=objective, slot_index=self._next_free_slot())
        self.active_tasks[task.task_id] = task
        asyncio.create_task(self._run_task(task))  # רץ במקביל למשימות קיימות
        return task.task_id

    async def _run_task(self, task: BrowserTask):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            await self._push(task, {"type": "TASK_ERROR",
                                     "detail": "Playwright אינו מותקן בסביבה זו."})
            return

        task.status = "running"
        x, y = _TILE_POSITIONS[task.slot_index]
        w, h = _TILE_SIZE
        async with async_playwright() as playwright:
            browser = await getattr(playwright, task.browser_choice).launch(
                headless=False,
                args=[f"--window-position={x},{y}", f"--window-size={w},{h}"],
            )
            context = await browser.new_context(viewport={"width": w, "height": h})
            page = await context.new_page()
            try:
                plan = await self._plan_steps(task.objective)
                for step in plan:
                    await self._execute_step(page, step, task)
                    task.steps_log.append(step)
                    await self._push(task, {"type": "TASK_UPDATE", "current_step": step})
                summary = self._summarize(task.steps_log)
                await self._push(task, {"type": "TASK_SUMMARY", "content": summary})
                task.status = "done"
            finally:
                await browser.close()

    async def _plan_steps(self, objective: str) -> list[str]:
        # Phase 2 מלא: קריאה ל-NIM (nemotron planning) לבניית תוכנית שלבים.
        return [f"חיפוש: {objective}", "פתיחת תוצאה ראשונה", "קריאת תוכן הדף"]

    async def _execute_step(self, page, step: str, task: BrowserTask):
        # תוכן דף שנקרא כאן הוא תמיד untrusted — בדיקת injection לפני שימוש.
        page_text = ""
        try:
            page_text = await page.inner_text("body")
        except Exception:  # noqa: BLE001
            pass
        hits = detect_injection_attempt(page_text) if page_text else []
        if hits:
            await self.gate.request(
                action_desc="הדף שנפתח ניסה להנחות פעולה — האם לאשר?",
                details={"patterns_detected": hits, "task_id": task.task_id},
                risk=RiskLevel.HIGH,
                source_untrusted=True,
            )

    def _summarize(self, steps_log: list[str]) -> str:
        return "בוצעו השלבים הבאים: " + "; ".join(steps_log)

    async def _push(self, task: BrowserTask, payload: dict):
        payload["task_id"] = task.task_id
        payload["task_label"] = f"משימה — {task.browser_choice}"
        await self.ws_manager.broadcast(payload)
