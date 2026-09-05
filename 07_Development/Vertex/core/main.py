"""
Vertex Orchestrator — נקודת הכניסה הראשית (מפרט §4.2, §16).

מריצים עם:  uvicorn core.main:app --host 127.0.0.1 --port 8420

עקרון-על: bind רק ל-127.0.0.1 (§10א1) — אין גישה מרחוק, אין שרת פתוח
לאינטרנט. כל תשובה טקסטואלית שיוצאת מכאן חייבת להיות בעברית (voice.tts).
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from core.config import load_config
from core.memory.db import VertexMemory
from core.modules.browser_automation import BrowserTaskManager
from core.modules.code_gen import CodeGenModule
from core.modules.file_ops import FileOpsModule
from core.modules.security_audit import run_security_audit
from core.nim_client.client import NimClient
from core.nim_client.model_router import model_for
from core.router.graph import VertexGraph, VertexState
from core.router.intent_classifier import classify_intent
from core.security.audit_log import AuditLog
from core.security.confirmation_gate import ConfirmationGate, RiskLevel
from core.voice.tts import HebrewTTS, enforce_hebrew_reply_language

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vertex")

CHAT_SYSTEM_PROMPT = enforce_hebrew_reply_language(
    "אתה Vertex — סוכן AI אישי, פרטי ומקומי, ששייך למשתמש בלבד. "
    "אתה עוזר עם ניהול קבצים, מחקר בדפדפן, כתיבת קוד ותחזוקת המחשב, "
    "תמיד תחת שליטתו המלאה: כל פעולה הרסנית עוברת אישור מפורש ממנו."
)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def create_app(config_path: str = "config.yaml") -> FastAPI:
    config = load_config(config_path)
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Vertex Orchestrator")

    ws_manager = ConnectionManager()
    audit_log = AuditLog(str(Path(config.data_dir) / "audit_log.db"))
    memory = VertexMemory(str(Path(config.data_dir) / "vertex_memory.db"))
    gate = ConfirmationGate(ws_manager, audit_log)
    tts = HebrewTTS(voice_gender=config.tts_voice_gender,
                     output_dir=str(Path(config.data_dir) / "tts_cache"))

    nim_client = NimClient(config.nim_api_key, cost_table=config.cost_table) if config.nim_api_key else None
    file_ops = FileOpsModule(gate, memory, audit_log)
    code_gen = CodeGenModule(gate, nim_client)
    browser_manager = BrowserTaskManager(ws_manager, gate, nim_client)

    def classify(text: str) -> str:
        model = model_for("intent_classification")
        return classify_intent(text, nim_client, model)

    graph = VertexGraph(classify)

    async def file_ops_node(state: VertexState) -> dict:
        # ניתוח פרמטרים בסיסי מתוך הבקשה; בפרודקשן מנותב דרך NIM לחילוץ מבנה.
        result = await file_ops.delete_matching(
            directory=state.result.get("directory", str(Path.home() / "Downloads")),
            pattern=state.result.get("pattern", "*.tmp"),
        )
        return {"reply": result.message, "affected": result.affected}

    async def security_audit_node(state: VertexState) -> dict:
        audit = run_security_audit()
        reply = (
            f"בדיקת האבטחה הושלמה. ציון סיכון: {audit['risk_score']}/100. "
            + " ".join(audit["recommendations"][:3])
        )
        return {"reply": reply, "audit": audit}

    async def memory_node(state: VertexState) -> dict:
        removed = memory.forget_matching(state.user_input)
        reply = f"נמחקו {removed} רשומות זיכרון תואמות." if removed else "לא נמצאה רשומה תואמת למחיקה."
        return {"reply": reply}

    async def browser_node(state: VertexState) -> dict:
        task_id = await browser_manager.add_task("chromium", state.user_input)
        return {"reply": "פתחתי משימת דפדפן חדשה — תוכל לעקוב אחריה בפאנל הצד.",
                "task_id": task_id}

    async def code_gen_node(state: VertexState) -> dict:
        return {"reply": "קיבלתי את בקשת הקוד. אשלח שאלות הבהרה אם יחסר מידע, "
                          "ולאחר מכן אציג diff לאישורך לפני כל שמירה."}

    async def ethovx_train_node(state: VertexState) -> dict:
        """
        משימת אימון ETHOVX — תמיד job מתוזמן ומאושר, לעולם לא 'רצה חופשי
        ברקע ומשתנה בעצמה' (§Scope, §9.2ד). דורשת אישור מפורש לפני הפעלה,
        ורצה כמשימת רקע כך שהצ'אט לא נחסם עד לסיום האימון.
        """
        approved = await gate.request(
            action_desc="הפעלת ריצת אימון ETHOVX על הקורפוס המאושר בהגדרות",
            details={"base_model": "Llama-3.2-3B (Ollama)"},
            risk=RiskLevel.MEDIUM,
        )
        if not approved:
            return {"reply": "האימון לא אושר — לא הופעלה שום ריצה."}

        approved_sources = config.ethovx.get("approved_sources", [])
        if not approved_sources:
            return {"reply": "לא הוגדרו מקורות קורפוס מאושרים (ethovx.approved_sources "
                              "ב-config.yaml). הוסף נתיבים ונסה שוב."}

        async def _run_and_report():
            from ethovx.train import run_training_job
            report = await asyncio.to_thread(
                run_training_job,
                config.ethovx.get("base_model", "llama3.2:3b"),
                approved_sources,
                str(Path(config.data_dir) / "ethovx_checkpoints"),
                audit_log,
            )
            await ws_manager.broadcast({"type": "TASK_SUMMARY", "task_id": "ethovx",
                                         "task_label": "אימון ETHOVX",
                                         "content": report.summary_text})

        asyncio.create_task(_run_and_report())
        return {"reply": "ריצת אימון ETHOVX הופעלה ברקע — אקבל דוח מסכם בסיום."}

    async def chat_node(state: VertexState) -> dict:
        if nim_client is None:
            return {"reply": "לא הוגדר מפתח NVIDIA NIM API עדיין — הגדר אותו בקובץ ההגדרות "
                              "כדי שאוכל לענות בצורה מלאה. בינתיים אני כאן ומקשיב."}
        messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": state.user_input},
        ]
        response = nim_client.chat_completion(model=model_for("chat"), messages=messages)
        return {"reply": nim_client.extract_text(response) or "לא הצלחתי לייצר תשובה כרגע."}

    graph.add_node("file_ops_node", file_ops_node)
    graph.add_node("browser_node", browser_node)
    graph.add_node("code_gen_node", code_gen_node)
    graph.add_node("security_audit_node", security_audit_node)
    graph.add_node("memory_node", memory_node)
    graph.add_node("ethovx_train_node", ethovx_train_node)
    graph.add_node("chat_node", chat_node)

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": "Vertex", "language": "he-IL"}

    @app.post("/api/security/audit")
    async def security_audit_endpoint():
        return run_security_audit()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            async for raw in ws.iter_text():
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "CONFIRM_RESOLVE":
                    gate.resolve(msg["task_id"], msg.get("approved", False))
                    continue

                if msg_type == "USER_MESSAGE":
                    state = VertexState(
                        user_input=msg["text"],
                        session_id=msg.get("session_id", "default"),
                        input_mode=msg.get("input_mode", "text"),
                    )
                    result = await graph.ainvoke(state)
                    reply_text = result.get("reply", "")
                    audio_path = ""
                    if reply_text:
                        audio_path = await tts.synthesize(reply_text)
                    await ws.send_json({
                        "type": "AGENT_REPLY",
                        "intent": result.get("intent"),
                        "text": reply_text,
                        "audio_path": audio_path,
                        "language": "he-IL",
                    })
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    logger.info("Vertex Orchestrator מוכן. bind=%s:%s", config.server_host, config.server_port)
    return app


app = create_app()
