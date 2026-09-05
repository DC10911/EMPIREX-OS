"""
State Machine של ה-Orchestrator (מפרט §4.2).

מימוש קל-משקל ללא תלות ב-LangGraph (כדי לצמצם תלויות בפריסה ראשונית) —
זהה בעקרון: router -> [file_ops_node | browser_node | code_gen_node |
security_audit_node | memory_node | chat_node]. ניתן להחליף בהמשך
במימוש LangGraph מלא (Phase 2) מבלי לשנות את חוזה ה-WebSocket.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRM = "awaiting_confirm"
    DONE = "done"
    FAILED = "failed"


@dataclass
class VertexState:
    user_input: str
    session_id: str
    input_mode: str = "text"
    intent: "str | None" = None
    status: TaskStatus = TaskStatus.PENDING
    result: dict = field(default_factory=dict)


NodeFn = Callable[[VertexState], Awaitable[dict]]


class VertexGraph:
    """State graph מינימלי: router -> node התואם לכוונה."""

    def __init__(self, classify_fn: Callable[[str], str]):
        self.classify_fn = classify_fn
        self.nodes: dict[str, NodeFn] = {}

    def add_node(self, name: str, fn: NodeFn):
        self.nodes[name] = fn

    async def ainvoke(self, state: VertexState) -> dict:
        intent = self.classify_fn(state.user_input)
        state.intent = intent
        node_name = f"{intent}_node"
        node = self.nodes.get(node_name, self.nodes.get("chat_node"))
        if node is None:
            return {"error": "לא נמצא מטפל לבקשה זו.", "intent": intent}
        state.status = TaskStatus.RUNNING
        try:
            result = await node(state)
            state.status = TaskStatus.DONE
            state.result = result
            return {"intent": intent, **result}
        except Exception as exc:  # noqa: BLE001
            state.status = TaskStatus.FAILED
            return {"intent": intent, "error": str(exc)}
