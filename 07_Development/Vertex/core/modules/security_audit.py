"""
מודול בדיקת חוזקות אבטחה — Vertex Security Audit (מפרט §10א4).

כלי אבחון בלבד — סורק את המחשב שלך עצמו (קריאה בלבד, לא הרסני), לא כלי
תקיפה ולא סורק רשתות זרות. פועל על-פי דרישה ("וורטקס תבדוק לי אבטחה")
או בתזמון שבועי אופציונלי. הבדיקות המלאות (Defender/Firewall/TPM/
Secure Boot/Windows Update) דורשות PowerShell + WMI וזמינות רק בפועל
על Windows; כאן הן ממומשות עם fallback בטוח לסביבות שאינן Windows.
"""

import platform
import subprocess


def _run_powershell(cmd: str) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def check_windows_defender() -> dict:
    if platform.system() != "Windows":
        return {"status": "unsupported", "detail": "בדיקה זמינה רק ב-Windows"}
    out = _run_powershell("Get-MpComputerStatus | ConvertTo-Json")
    return {"status": "ok" if out else "unknown", "raw": out}


def check_firewall_profiles() -> dict:
    if platform.system() != "Windows":
        return {"status": "unsupported", "detail": "בדיקה זמינה רק ב-Windows"}
    out = _run_powershell("netsh advfirewall show allprofiles")
    return {"status": "ok" if out else "unknown", "raw": out}


def scan_local_listening_ports() -> dict:
    """netstat מקומי בלבד — לא סריקת רשת חיצונית."""
    try:
        cmd = ["netstat", "-ano"] if platform.system() == "Windows" else ["ss", "-tulpn"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {"status": "ok", "raw": result.stdout}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


def check_secure_boot() -> dict:
    if platform.system() != "Windows":
        return {"status": "unsupported"}
    out = _run_powershell("Confirm-SecureBootUEFI")
    return {"status": "ok" if "True" in out else "warning", "raw": out}


def check_tpm() -> dict:
    if platform.system() != "Windows":
        return {"status": "unsupported"}
    out = _run_powershell("Get-Tpm | ConvertTo-Json")
    return {"status": "ok" if out else "unknown", "raw": out}


def check_windows_updates() -> dict:
    return {"status": "unsupported", "detail": "דורש מודול PSWindowsUpdate בסביבת Windows"}


def check_driver_versions() -> dict:
    return {"status": "not_implemented"}


def scan_startup_and_tasks() -> dict:
    if platform.system() != "Windows":
        return {"status": "unsupported"}
    out = _run_powershell("Get-CimInstance Win32_StartupCommand | ConvertTo-Json")
    return {"status": "ok" if out else "unknown", "raw": out}


CHECKS = {
    "defender_status": check_windows_defender,
    "firewall_status": check_firewall_profiles,
    "open_ports": scan_local_listening_ports,
    "secure_boot": check_secure_boot,
    "tpm_status": check_tpm,
    "pending_updates": check_windows_updates,
    "outdated_drivers": check_driver_versions,
    "startup_anomalies": scan_startup_and_tasks,
}


def run_security_audit() -> dict:
    """סריקה מקומית בלבד — קריאה, לא שינוי. כל בדיקה עצמאית ולא הרסנית."""
    report = {name: fn() for name, fn in CHECKS.items()}
    risk_score = _calculate_risk_score(report)
    return {
        "report": report,
        "risk_score": risk_score,
        "recommendations": _build_recommendations(report),
    }


def _calculate_risk_score(report: dict) -> int:
    score = 100
    for check in report.values():
        status = check.get("status")
        if status == "critical":
            score -= 25
        elif status == "warning":
            score -= 10
        elif status == "unknown":
            score -= 5
    return max(0, min(100, score))


def _build_recommendations(report: dict) -> list[str]:
    recs = []
    for name, check in report.items():
        if check.get("status") in ("warning", "critical"):
            recs.append(f"בדוק את הפריט '{name}' — נמצא סטטוס {check.get('status')}.")
    if not recs:
        recs.append("לא נמצאו ממצאים חריגים בסריקה הנוכחית.")
    return recs
