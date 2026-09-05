"""
Audit Log — יומן פעולות עם Hash-Chain (מפרט §22.2, §19).

כל רשומה כוללת hash של הרשומה הקודמת. שינוי/מחיקה כלשהי באמצע השרשרת
שוברת את ה-hash של כל מה שאחריה — ניתנת לזיהוי מיידי ע"י verify_chain().
זהו יומן היסטורי בלבד: קריאה בלבד, לא נמחק אוטומטית לעולם (§25).
"""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

GENESIS_HASH = "0" * 64


class AuditLog:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def _last_hash(self) -> str:
        row = self.conn.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS_HASH

    def write(self, event_type: str, **payload) -> str:
        with self._lock:
            prev_hash = self._last_hash()
            timestamp = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
            entry_hash = hashlib.sha256(
                f"{prev_hash}{event_type}{payload_json}{timestamp}".encode("utf-8")
            ).hexdigest()
            self.conn.execute(
                "INSERT INTO audit_entries (event_type, payload, timestamp, prev_hash, entry_hash) "
                "VALUES (?,?,?,?,?)",
                (event_type, payload_json, timestamp, prev_hash, entry_hash),
            )
            self.conn.commit()
            return entry_hash

    def verify_chain(self) -> tuple[bool, "int | None"]:
        """מחזיר (תקין?, מספר הרשומה שנשברה אם לא תקין)."""
        rows = self.conn.execute(
            "SELECT id, event_type, payload, timestamp, prev_hash, entry_hash "
            "FROM audit_entries ORDER BY id ASC"
        ).fetchall()
        expected_prev = GENESIS_HASH
        for row_id, event_type, payload_json, timestamp, prev_hash, entry_hash in rows:
            if prev_hash != expected_prev:
                return False, row_id
            recomputed = hashlib.sha256(
                f"{prev_hash}{event_type}{payload_json}{timestamp}".encode("utf-8")
            ).hexdigest()
            if recomputed != entry_hash:
                return False, row_id
            expected_prev = entry_hash
        return True, None

    def tail(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT event_type, payload, timestamp FROM audit_entries ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"event_type": e, "payload": json.loads(p), "timestamp": t}
            for e, p, t in rows
        ]

    def close(self):
        self.conn.close()
