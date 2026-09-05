"""
מודול כתיבת קוד — Phase 2 (מפרט §7, §18.4).

זרימה מחייבת: (1) הבנת דרישה + שאלות הבהרה, (2) כתיבת קוד+טסטים,
(3) הרצה ב-sandbox מבודד (לא על המערכת החיה), (4) הצגת diff+תוצאות,
(5) שמירה/הרצה בפועל רק אחרי אישור מפורש (confirmation_gate).

ה-sandbox האמיתי (Docker/WSL2 מבודד ללא גישת רשת/דיסק חי) ממומש
בפרודקשן; כאן ה-stub מריץ בדיקה סטטית (bandit אם מותקן) כשלב ביניים
לפני שמגיעים ל-confirmation_gate, כדי לא "לדמות" sandbox שלא קיים.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.security.confirmation_gate import ConfirmationGate, RiskLevel


@dataclass
class CodeGenResult:
    approved: bool
    code: str
    static_scan_report: str
    message: str


class CodeGenModule:
    def __init__(self, gate: ConfirmationGate, nim_client=None):
        self.gate = gate
        self.nim_client = nim_client

    def static_scan(self, code: str) -> str:
        """הרצת bandit על הקוד שנוצר לפני הצגתו למשתמש (§17 שורה 6)."""
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name
        try:
            result = subprocess.run(
                ["bandit", "-q", "-f", "txt", tmp_path],
                capture_output=True, text=True, timeout=20,
            )
            return result.stdout or "לא נמצאו ממצאי אבטחה סטטיים."
        except FileNotFoundError:
            return "bandit אינו מותקן בסביבה זו — יש להריץ סריקה ידנית לפני אישור."
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def propose_and_confirm(self, generated_code: str, description: str) -> CodeGenResult:
        scan_report = self.static_scan(generated_code)
        approved = await self.gate.request(
            action_desc=f"שמירה/הרצה של קוד שנוצר עבור: {description}",
            details={"code_preview": generated_code[:2000], "static_scan": scan_report},
            risk=RiskLevel.HIGH,
        )
        message = (
            "הקוד אושר ונשמר בפועל." if approved
            else "הקוד לא אושר — לא בוצעה שום כתיבה למערכת החיה."
        )
        return CodeGenResult(approved=approved, code=generated_code,
                              static_scan_report=scan_report, message=message)
