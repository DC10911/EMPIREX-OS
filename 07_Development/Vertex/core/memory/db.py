"""
זיכרון מתמיד של Vertex (מפרט §8).

בפרודקשן על Windows יש להשתמש ב-sqlcipher3 להצפנת AES-256 של הקובץ
(מפתח נגזר מ-Windows DPAPI, ר' §10א2). כאן נשתמש ב-sqlite3 הרגיל עם
נסיון fallback אוטומטי ל-sqlcipher3 אם הוא מותקן — כדי שהקוד ירוץ גם
בסביבת פיתוח לינוקס וגם בפרודקשן על Windows.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import sqlcipher3 as _sqlcipher  # type: ignore
    _HAS_SQLCIPHER = True
except ImportError:
    _HAS_SQLCIPHER = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    category TEXT,                -- 'profile' | 'project' | 'preference'
    content TEXT,
    source_conversation TEXT,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    started_at DATETIME,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS tasks_history (
    id TEXT PRIMARY KEY,
    task_type TEXT,               -- 'file_ops' | 'browser' | 'code_gen' | 'ethovx'
    description TEXT,
    status TEXT,
    result_summary TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS undo_log (
    id TEXT PRIMARY KEY,
    action_type TEXT,             -- 'delete' | 'move' | 'rename'
    payload TEXT,                 -- JSON: מיפוי מקור->יעד לכל קובץ
    created_at DATETIME,
    reverted INTEGER DEFAULT 0
);
"""


class VertexMemory:
    """
    שכבת גישה לזיכרון הקבוע. תומכת במחיקה נקודתית ("וורטקס תשכח את X")
    ובייצוא מלא לגיבוי, לפי §8.2.
    """

    def __init__(self, db_path: str, encryption_key: "str | None" = None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        if _HAS_SQLCIPHER and encryption_key:
            self.conn = _sqlcipher.connect(db_path)
            self.conn.execute(f"PRAGMA key = '{encryption_key}'")
            self.encrypted = True
        else:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.encrypted = False
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def remember_fact(self, category: str, content: str, source_conversation: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO facts (category, content, source_conversation, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (category, content, source_conversation, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def forget_fact(self, fact_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def forget_matching(self, keyword: str) -> int:
        """'וורטקס תשכח את X' — מחיקת כל עובדה שמכילה את keyword."""
        cur = self.conn.execute("DELETE FROM facts WHERE content LIKE ?", (f"%{keyword}%",))
        self.conn.commit()
        return cur.rowcount

    def list_facts(self, category: "str | None" = None) -> list[dict]:
        if category:
            rows = self.conn.execute(
                "SELECT id, category, content, created_at FROM facts WHERE category = ? ORDER BY id DESC",
                (category,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, category, content, created_at FROM facts ORDER BY id DESC"
            ).fetchall()
        return [{"id": r[0], "category": r[1], "content": r[2], "created_at": r[3]} for r in rows]

    def wipe_all(self):
        """מחיקה מלאה של הזיכרון — פעולה שחייבת לעבור confirmation_gate ברמת הקורא."""
        self.conn.executescript(
            "DELETE FROM facts; DELETE FROM conversations; DELETE FROM tasks_history;"
        )
        self.conn.commit()

    def log_task(self, task_type: str, description: str, status: str, result_summary: str = ""):
        self.conn.execute(
            "INSERT INTO tasks_history (id, task_type, description, status, result_summary, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), task_type, description, status, result_summary,
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def write_undo_log(self, action_type: str, payload_json: str) -> str:
        undo_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO undo_log (id, action_type, payload, created_at) VALUES (?,?,?,?)",
            (undo_id, action_type, payload_json, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return undo_id

    def get_last_undo(self) -> "dict | None":
        row = self.conn.execute(
            "SELECT id, action_type, payload FROM undo_log WHERE reverted = 0 "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "action_type": row[1], "payload": row[2]}

    def mark_undo_reverted(self, undo_id: str):
        self.conn.execute("UPDATE undo_log SET reverted = 1 WHERE id = ?", (undo_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
