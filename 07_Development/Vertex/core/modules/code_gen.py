"""
מודול כתיבת קוד — Phase 2 (מפרט §7, §18.4).

זרימה מחייבת (§7 טבלה):
  1. הבנת דרישה + שאלות הבהרה אם חסר מידע (לא מנחש בשקט).
  2. כתיבת קוד + טסטים בסיסיים.
  3. הרצת טסטים בסביבת sandbox מבודדת (Docker, --network none) —
     לא על המערכת החיה.
  4. הצגת diff/קובץ סופי + תוצאת טסטים + סריקה סטטית (bandit) בצ'אט.
  5. רק אחרי אישורך המפורש — שמירה בפועל / הרצה על המערכת האמיתית.

אם ה-sandbox (Docker) אינו זמין בסביבה — Code-Gen לא "מדלג" עליו
בשקט: הוא מדווח על כך במפורש בכרטיס האישור, כדי שתדע שהקוד לא נבדק
דינמית לפני שאתה מאשר.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.modules.sandbox_runner import SandboxRunResult, run_in_sandbox
from core.security.confirmation_gate import ConfirmationGate, RiskLevel


@dataclass
class CodeGenResult:
    approved: bool
    code: str
    static_scan_report: str
    sandbox_result: SandboxRunResult
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

    async def propose_and_confirm(self, generated_code: str, description: str,
                                   test_code: str = "") -> CodeGenResult:
        scan_report = self.static_scan(generated_code)
        sandbox_result = run_in_sandbox(generated_code, test_code)

        details = {
            "code_preview": generated_code[:2000],
            "static_scan": scan_report,
            "sandbox_status": sandbox_result.status,
            "sandbox_stdout": sandbox_result.stdout[:1000],
            "sandbox_stderr": sandbox_result.stderr[:1000],
        }
        # אם ה-sandbox לא זמין או הקוד נכשל בו — זה high risk מוגבר, לא רק
        # "מציג ומבקש אישור" רגיל; המשתמש חייב לראות את זה בבירור.
        risk = RiskLevel.HIGH

        approved = await self.gate.request(
            action_desc=f"שמירה/הרצה של קוד שנוצר עבור: {description} "
                        f"(סטטוס sandbox: {sandbox_result.status})",
            details=details,
            risk=risk,
        )
        message = (
            "הקוד אושר ונשמר בפועל." if approved
            else "הקוד לא אושר — לא בוצעה שום כתיבה למערכת החיה."
        )
        return CodeGenResult(approved=approved, code=generated_code,
                              static_scan_report=scan_report,
                              sandbox_result=sandbox_result, message=message)
