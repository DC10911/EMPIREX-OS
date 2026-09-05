"""
ETHOVX Corpus Manager (מפרט §9.1 שלב 2, §19.3).

אוסף/מארגן חומר אימון **רק ממקורות שאישרת במפורש** (קבצים/אתרים
מוגדרים ב-config.yaml תחת ethovx.approved_sources) — לעולם לא "סורק
את כל האינטרנט". כל ריצת אימון נרשמת עם hash SHA-256 מדויק של הקורפוס
ששימש בפועל, כדי שהריצה תהיה בת-שחזור מלא (Repudiation mitigation,
§19.3), ומוצגת לך דגימה אקראית של 10% מהקורפוס לפני job (הגנה מפני
data poisoning).
"""

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CorpusSnapshot:
    files: list[str]
    total_chars: int
    corpus_hash: str
    sample_for_review: list[str]


def build_corpus(approved_paths: list[str], sample_ratio: float = 0.10) -> CorpusSnapshot:
    """
    בונה קורפוס אימון אך ורק מהנתיבים המאושרים. מחזיר גם דגימה אקראית
    להצגה למשתמש לפני job (§19.3: 'סקירת דגימה אקראית 10% מהקורפוס
    מוצגת לך לפני job').
    """
    collected_files: list[Path] = []
    for raw_path in approved_paths:
        p = Path(raw_path).expanduser()
        if p.is_file():
            collected_files.append(p)
        elif p.is_dir():
            collected_files.extend(sorted(p.rglob("*.txt")) + sorted(p.rglob("*.md")))

    hasher = hashlib.sha256()
    total_chars = 0
    file_paths_str = []
    for f in sorted(collected_files):
        content = f.read_text(encoding="utf-8", errors="ignore")
        hasher.update(content.encode("utf-8"))
        total_chars += len(content)
        file_paths_str.append(str(f))

    sample_n = max(1, int(len(file_paths_str) * sample_ratio)) if file_paths_str else 0
    sample = random.sample(file_paths_str, min(sample_n, len(file_paths_str))) if file_paths_str else []

    return CorpusSnapshot(
        files=file_paths_str,
        total_chars=total_chars,
        corpus_hash=hasher.hexdigest(),
        sample_for_review=sample,
    )


def save_snapshot_manifest(snapshot: CorpusSnapshot, out_path: str):
    """שומר manifest בר-ביקורת של הקורפוס המדויק ששימש לריצת אימון נתונה."""
    Path(out_path).write_text(
        json.dumps({
            "corpus_hash": snapshot.corpus_hash,
            "file_count": len(snapshot.files),
            "total_chars": snapshot.total_chars,
            "files": snapshot.files,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
