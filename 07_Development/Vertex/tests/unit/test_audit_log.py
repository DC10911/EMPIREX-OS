import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.security.audit_log import AuditLog


def _make_log(tmp_path: Path) -> AuditLog:
    return AuditLog(str(tmp_path / "audit.db"))


def test_write_and_verify_chain(tmp_path):
    log = _make_log(tmp_path)
    log.write("EVENT_A", foo="bar")
    log.write("EVENT_B", count=3)
    valid, broken_at = log.verify_chain()
    assert valid is True
    assert broken_at is None


def test_tamper_detected(tmp_path):
    db_path = tmp_path / "audit.db"
    log = AuditLog(str(db_path))
    log.write("EVENT_A", foo="bar")
    log.write("EVENT_B", count=3)
    log.close()

    # תקיפה מדומה: עריכה ידנית של payload של רשומה אמצעית
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE audit_entries SET payload = ? WHERE id = 1", ('{"foo": "TAMPERED"}',))
    conn.commit()
    conn.close()

    log2 = AuditLog(str(db_path))
    valid, broken_at = log2.verify_chain()
    assert valid is False
    assert broken_at == 1


def test_secrets_never_logged_by_gate(tmp_path):
    from core.security.confirmation_gate import _safe
    details = {"api_key": "sk-secret", "files": ["a.txt"]}
    safe = _safe(details)
    assert "api_key" not in safe
    assert safe["files"] == ["a.txt"]
