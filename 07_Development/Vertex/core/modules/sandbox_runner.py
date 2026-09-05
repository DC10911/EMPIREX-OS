"""
Sandbox Runner — הרצת קוד שנוצר בתוך container מבודד (מפרט §10א1, §18.4).

עיקרון: הרצה ראשונית תמיד בתוך container מבודד (Docker), ללא גישת רשת
וללא גישה לכונן האמיתי. מעבר לדיסק החי (כתיבה בפועל למערכת שלך) קורה
רק אחרי אישור מפורש דרך confirmation_gate + סריקה סטטית (bandit).

אם Docker אינו מותקן בסביבה (למשל בזמן פיתוח ראשוני) — הפונקציה
מחזירה סטטוס 'sandbox_unavailable' בבירור, ולעולם לא "מדמה" הרצה
בטוחה שלא התקיימה בפועל. Code-Gen module חוסם מעבר לאישור אם
הסביבה לא זמינה, ומציג זאת למשתמש כפי שהוא.
"""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DOCKER_IMAGE = "python:3.12-slim"
TIMEOUT_SEC = 20


@dataclass
class SandboxRunResult:
    status: str          # "ok" | "runtime_error" | "timeout" | "sandbox_unavailable"
    stdout: str
    stderr: str
    exit_code: "int | None"


def docker_available() -> bool:
    return shutil.which("docker") is not None


def run_in_sandbox(code: str, test_code: str = "") -> SandboxRunResult:
    """
    מריץ code (+ test_code אופציונלי) בתוך container Docker חד-פעמי:
    --network none (ללא גישת רשת), --rm (נמחק מיד בסיום), ומאונט
    read-only של קובץ הקוד בלבד — לא של כונן המערכת.
    """
    if not docker_available():
        return SandboxRunResult(
            status="sandbox_unavailable",
            stdout="",
            stderr="Docker אינו מותקן בסביבה זו — יש להתקין Docker Desktop "
                   "לפני שניתן להריץ קוד שנוצר, אפילו לבדיקה.",
            exit_code=None,
        )

    workdir = Path(tempfile.mkdtemp(prefix="vertex_sandbox_"))
    try:
        script_path = workdir / "generated.py"
        script_path.write_text(code, encoding="utf-8")
        if test_code:
            (workdir / "test_generated.py").write_text(test_code, encoding="utf-8")
            entry = "python -m pytest -q test_generated.py"
        else:
            entry = "python generated.py"

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "1",
            "-v", f"{workdir}:/sandbox:ro",
            "-w", "/sandbox",
            DOCKER_IMAGE,
            "sh", "-c", entry,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC)
            status = "ok" if result.returncode == 0 else "runtime_error"
            return SandboxRunResult(status=status, stdout=result.stdout,
                                     stderr=result.stderr, exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            return SandboxRunResult(status="timeout", stdout="",
                                     stderr=f"חריגה מזמן ריצה מותר ({TIMEOUT_SEC}s).",
                                     exit_code=None)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
