"""
טעינת תצורה (מפרט §10, §14).

מפתח ה-NVIDIA NIM API לעולם לא נשמר כטקסט גלוי ב-config.yaml. בפרודקשן
על Windows יש להשתמש ב-Windows Credential Manager (DPAPI) — פונקציות
save_secret_windows/load_secret_windows מיושמות עם pywin32 ומופעלות
רק כאשר platform.system() == "Windows". בסביבת פיתוח (כולל לינוקס),
המפתח נטען ממשתנה סביבה VERTEX_NIM_API_KEY בלבד — אף פעם לא מקובץ.
"""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

import yaml

APP_NAME = "Vertex"
CREDENTIAL_TARGET = "Vertex_NVIDIA_NIM_API_KEY"


@dataclass
class VertexConfig:
    install_dir: str
    data_dir: str
    tts_voice_gender: str = "female"
    language: str = "he-IL"
    wake_word_threshold: float = 0.55
    server_host: str = "127.0.0.1"   # לעולם לא 0.0.0.0 — ר' §10א1
    server_port: int = 8420
    nim_api_key: str = field(default="", repr=False)
    cost_table: dict = field(default_factory=dict)


def default_data_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", str(Path.home()))
        return str(Path(base) / APP_NAME)
    return str(Path.home() / f".{APP_NAME.lower()}")


def load_config(config_path: str = "config.yaml") -> VertexConfig:
    data: dict = {}
    p = Path(config_path)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    api_key = os.environ.get("VERTEX_NIM_API_KEY", "")
    if not api_key and platform.system() == "Windows":
        api_key = load_secret_windows(CREDENTIAL_TARGET) or ""

    return VertexConfig(
        install_dir=data.get("install_dir", str(Path(config_path).resolve().parent)),
        data_dir=data.get("data_dir", default_data_dir()),
        tts_voice_gender=data.get("tts_voice_gender", "female"),
        language=data.get("language", "he-IL"),
        wake_word_threshold=float(data.get("wake_word_threshold", 0.55)),
        server_host=data.get("server_host", "127.0.0.1"),
        server_port=int(data.get("server_port", 8420)),
        nim_api_key=api_key,
        cost_table=data.get("cost_table", {}),
    )


def save_secret_windows(target: str, secret: str) -> bool:
    """שמירת סוד ב-Windows Credential Manager (DPAPI) — Windows בלבד."""
    if platform.system() != "Windows":
        return False
    try:
        import win32cred  # type: ignore
        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "CredentialBlob": secret.encode("utf-16-le"),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)
        return True
    except ImportError:
        return False


def load_secret_windows(target: str) -> "str | None":
    if platform.system() != "Windows":
        return None
    try:
        import win32cred  # type: ignore
        cred = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
        return cred["CredentialBlob"].decode("utf-16-le")
    except ImportError:
        return None
    except Exception:  # noqa: BLE001 — לא נמצא cred קיים
        return None
