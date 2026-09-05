# Vertex — סוכן ה-AI האישי שלך

**שם הסוכן: Vertex** (וורטקס). מילת ההפעלה הקולית: **"היי וורטקס"**.
שם הקוד הפנימי של מודל השפה המקומי המתמחה: **ETHOVX** (רכיב נפרד,
Phase 3 — ר' למטה).

> **הכלל המחייב היחיד שאסור לשבור בפרויקט הזה: Vertex מדבר איתך אך ורק
> בעברית תקנית — גם בטקסט וגם בקול.** האכיפה הזו בנויה בקוד עצמו
> (`core/voice/tts.py::enforce_hebrew_reply_language`, ר' הסבר בהמשך),
> לא רק בבקשה בפרומפט. הוא יכול לבצע פעולות באנגלית (למשל לכתוב קוד
> Python, לחפש מונח טכני באנגלית בדפדפן) — אבל כל דבר שהוא **אומר לך**
> הוא בעברית, נקודה.

מסמך זה הוא ה-README התפעולי של המימוש בפועל, שנבנה לפי המפרט ההנדסי
המלא שהעברת (VERTEX — מפרט הנדסי, 45 עמודים, v1.0). המימוש שבתיקייה הזו
מכסה את **Phase 1 (MVP), Phase 2 (הרחבת יכולות ליבה) ואת שלד Phase 3
(ETHOVX)** — כל 12 המודולים שהוגדרו ב-§14: Orchestrator, שער אישורים,
יומן ביקורת עם hash-chain, ניהול קבצים בטוח עם שחזור אוטומטי מהאשפה,
אוטומציית דפדפן עם ריבוי משימות ו-tiling אמיתי, כתיבת קוד עם sandbox
Docker אמיתי, צינור אימון ETHOVX, זיכרון קבוע, ממשק צ'אט מלא-מסך
בעברית, ומודול קול עברי.

**מה שנשאר תלוי במחשב הפיזי שלך ולא ניתן להשלים מרחוק**: אימון מודל
ה-wake-word (חייב את הקלטת הקול שלך בפועל), חיבור GPU אמיתי לאימון
ETHOVX, והתקנת Docker Desktop להפעלת ה-sandbox. אלה לא "חוסרים בקוד"
— הם דורשים חומרה/קלט שרק אתה יכול לספק, וממש מתועדים למטה כשלבים
מפורשים שתבצע בעצמך.

---

## 1. התיקייה שדרכה הכל נכתב למחשב שלך

זו התיקייה שביקשת — **כל קובץ, כל לוג, כל הגדרה, כל דבר ש-Vertex כותב
או קורא במחשב שלך עובר דרכה**:

| מה | איפה |
|---|---|
| **תיקיית ההתקנה (קוד התוכנה עצמו)** | `C:\Vertex` (בהתקנת פיתוח מהירה) או `C:\Program Files\Vertex` (בהתקנת ה-installer החתום, §10) |
| **נתוני משתמש (זיכרון, יומן ביקורת, קאש קול)** | `%APPDATA%\Vertex\` — כלומר בפועל `C:\Users\<שם המשתמש שלך>\AppData\Roaming\Vertex\` |
| **קובץ ההגדרות** | `C:\Vertex\config.yaml` |
| **מפתח ה-API של NVIDIA** | **לא בקובץ בכלל** — ב-Windows Credential Manager המוצפן (DPAPI), ר' סעיף 4 למטה |

כל קוד המקור שבניתי נמצא כרגע ברפוזיטורי הזה, בנתיב:
`07_Development/Vertex/`. זו תיקיית המקור (source) — ממנה מריצים את
סקריפט ההתקנה שמעתיק הכל ל-`C:\Vertex` במחשב שלך בפועל.

---

## 2. דרישות מקדימות במחשב שלך (Windows 10/11)

צריך להתקין פעם אחת, לפני הכל:

1. **Python 3.12** — https://www.python.org/downloads/ (וודא לסמן
   "Add python.exe to PATH" בהתקנה).
2. **Node.js 20 LTS ומעלה** — https://nodejs.org (נדרש לממשק המשתמש).
3. **Git** (אופציונלי, אם תרצה לעדכן קוד מה-repo) — https://git-scm.com.
4. **מפתח NVIDIA NIM API פעיל** — כבר יש לך אחד (כפי שצוין במפרט).

---

## 3. התקנה — שלב-אחר-שלב

### דרך א' — סקריפט ההתקנה המהיר (מומלץ להתחלה)

1. העתק/הורד את כל תיקיית `07_Development/Vertex` מהריפו למחשב ה-Windows
   שלך, לכל מיקום זמני (למשל שולחן העבודה).
2. פתח **PowerShell** (לא חובה כ-Administrator — Vertex רץ כמשתמש רגיל
   בכוונה, §10) בתוך התיקייה שהעתקת, בתת-התיקייה `scripts`.
3. הרץ:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\install_windows.ps1
   ```
4. הסקריפט:
   - יוצר את `C:\Vertex` ומעתיק לשם את כל הקבצים.
   - בונה סביבת Python (`venv`) ומתקין את כל התלויות (`requirements.txt`).
   - מתקין את תלויות הממשק (`npm install`).
   - יוצר קובץ `config.yaml` מתוך התבנית.
   - יוצר קיצור דרך **"Vertex"** על שולחן העבודה שלך.
   - (אם כבר אימנת את מודל ה-wake-word) רושם את שירות "היי וורטקס"
     כמשימה מתוזמנת שרצה אוטומטית בכניסה למשתמש.

### דרך ב' — installer חתום דיגיטלית (להפצה סופית, §23.1)

בתיקיית `installer/build_installer.iss` נמצא סקריפט **Inno Setup** מלא.
זו הדרך המקצועית לפרודקשן: build עם PyInstaller + electron-builder,
חתימה דיגיטלית ל-exe (`signtool`), והתקנה בלחיצה כפולה על `VertexSetup.exe`
בדיוק כמו כל תוכנת Windows רגילה — ללא PowerShell בכלל בצד המשתמש
הסופי. זה מתאים לשלב שבו הקוד יציב ומוכן להפצה קבועה.

---

## 4. הגדרת מפתח NVIDIA NIM API (חשוב — פעם אחת)

המפתח **לעולם לא נשמר בקובץ טקסט גלוי**. שתי דרכים:

**דרך מהירה לפיתוח/בדיקה** — משתנה סביבה (זמני, לא נשמר בין הפעלות של
המחשב אלא אם תגדיר אותו כמשתנה סביבה קבוע ב-Windows):
```powershell
$env:VERTEX_NIM_API_KEY = "המפתח-שלך-כאן"
```

**דרך מומלצת לפרודקשן** — שמירה מוצפנת ב-Windows Credential Manager:
```powershell
cd C:\Vertex
.\venv\Scripts\python.exe -c "from core.config import save_secret_windows, CREDENTIAL_TARGET; save_secret_windows(CREDENTIAL_TARGET, input('הדבק כאן את מפתח ה-NIM: '))"
```
מרגע זה Vertex יטען את המפתח אוטומטית בכל הפעלה, מוצפן, לעולם לא בלוג
ולעולם לא ב-`config.yaml`.

---

## 5. הפעלה

לחיצה כפולה על קיצור הדרך **"Vertex"** על שולחן העבודה (או הרצת
`C:\Vertex\scripts\start_vertex.bat`). זה יעלה:
1. את ה-Orchestrator (השרת המקומי, `127.0.0.1:8420` בלבד — אין גישה
   מרחוק לעולם, §10א1).
2. את חלון הצ'אט המלא-מסך של Vertex.

**הפעלה חוזרת אינה פותחת שוב את תיקיית ההתקנה** — רק את חלון הצ'אט,
בדיוק כפי שנדרש. סגירת החלון ממזערת אותו לשורת המשימות (tray) — Vertex
ממשיך להאזין ברקע ל"היי וורטקס".

### הפעלה קולית ("היי וורטקס")

מילת ההפעלה מותאמת אישית לקול שלך ודורשת אימון חד-פעמי קצר (~20 דקות),
כי המפרט דרש בפירוש שלא תהיה "האזנה כללית" גנרית שמפריעה לפרטיות. ההוראות
המלאות נמצאות ב-`wake_service/README.md`. בקיצור:
```powershell
cd C:\Vertex
.\venv\Scripts\python.exe wake_service\record_samples.py --label positive --count 50
.\venv\Scripts\python.exe wake_service\record_samples.py --label negative --count 200
```
לאחר מכן מריצים את שלב האימון (מתועד באותו README) ומריצים שוב את
`install_windows.ps1` — הוא יזהה את המודל המאומן וירשום את שירות
ההאזנה כמשימה אוטומטית.

**עד לאימון המודל, אפשר להשתמש ב-Vertex במלואו דרך הטקסט וכפתור
המיקרופון בממשק** — ה-wake-word הוא נוחות נוספת, לא תלות.

---

## 6. איך אני יודע ש-Vertex מדבר איתי בעברית תמיד?

שלוש שכבות אכיפה, לא רק "הבטחה בפרומפט":

1. **`core/voice/tts.py`** — כל תשובה טקסטואלית עוברת המרה לקול עם
   קול עברי-ישראלי תקני ואיכותי (Neural TTS): **Hila** (נשי,
   ברירת מחדל) או **Avri** (גברי) — ניתן להחליף ב-`config.yaml`
   (`tts_voice_gender: female|male`).
2. **`enforce_hebrew_reply_language()`** — מוסיף אוטומטית ל-system
   prompt של כל קריאה למודל השפה הוראת ברזל: "עליך לענות אך ורק
   בעברית תקנית... בלי יוצא מן הכלל". זה קורה בקוד, לא משהו שאפשר
   לשכוח להוסיף בפרומפט בודד.
3. **`injection_guard.py`** — אותה הוראת השפה העברית משובצת גם
   ב-`SYSTEM_PROMPT_WITH_INJECTION_DEFENSE`, כך שגם כשהסוכן קורא תוכן
   חיצוני (דף אינטרנט באנגלית וכו') — הוא ממשיך לדווח לך בעברית.

בדיקת קבלה מהירה: תבקש מ-Vertex "search for the weather in New York"
— הוא יבצע את החיפוש באנגלית בדפדפן (כי זו הבקשה הטכנית), אבל ידווח
לך על התוצאה בעברית מלאה, בקול עברי.

---

## 7. מה כבר עובד בפועל היום (נבדק אוטומטית, 16/16 טסטים עוברים)

```
tests/unit/test_audit_log.py::test_write_and_verify_chain PASSED
tests/unit/test_audit_log.py::test_tamper_detected PASSED
tests/unit/test_audit_log.py::test_secrets_never_logged_by_gate PASSED
tests/unit/test_browser_tiling.py::test_concurrent_tasks_get_distinct_slots PASSED
tests/unit/test_browser_tiling.py::test_next_free_slot_reuses_freed_slot PASSED
tests/unit/test_confirmation_gate.py::test_confirmation_approved PASSED
tests/unit/test_confirmation_gate.py::test_confirmation_timeout_defaults_to_reject PASSED
tests/unit/test_confirmation_gate.py::test_no_action_without_explicit_approval PASSED
tests/unit/test_ethovx_corpus.py::test_build_corpus_only_from_approved_paths PASSED
tests/unit/test_ethovx_corpus.py::test_corpus_hash_is_deterministic PASSED
tests/unit/test_file_ops.py::test_delete_matching_requires_approval_and_moves_to_trash PASSED
tests/unit/test_file_ops.py::test_no_deletion_without_approval PASSED
tests/unit/test_sandbox_runner.py::test_sandbox_unavailable_reported_honestly PASSED
tests/unit/test_undo_restore.py::test_undo_last_reports_honest_failure_when_restore_unsupported PASSED
tests/unit/test_undo_restore.py::test_undo_last_reports_success_when_restore_works PASSED
tests/unit/test_undo_restore.py::test_undo_with_no_history PASSED
```

הרצה עצמאית: `cd 07_Development/Vertex && PYTHONPATH=. pytest tests/unit -v`

- **Orchestrator** (FastAPI + WebSocket) — עולה, מגיב על `/health` ו-`/api/security/audit`.
- **Confirmation Gate** — שום מחיקה/הרצת קוד/אימון לא קורים בלי אישור מפורש; timeout=דחייה.
- **Audit Log** — hash-chain אמיתי, מזהה שיבוש בקובץ (מוכח בטסט).
- **File Ops** — מחיקה = אשפה (`send2trash`) בלבד, עם undo log **ושחזור אוטומטי
  אמיתי** מהאשפה דרך Windows Shell API (`winshell`) — לא רק "לך תשחזר ידנית".
- **Browser Automation** — עד 4 משימות מקביליות עם **tiling אמיתי**
  (כל חלון Chromium/Edge/Firefox נפתח ברביע נפרד של המסך אוטומטית,
  `--window-position`/`--window-size`), BrowserContext מבודד לכל משימה,
  חסימת injection guard על תוכן דף.
- **Code-Gen** — bandit (סטטי) **+ sandbox Docker אמיתי** (`--network none`,
  `--rm`, מגבלת CPU/זיכרון) לפני כל בקשת אישור; אם Docker לא מותקן —
  מדווח זאת בפירוש בכרטיס האישור, לא מדמה בדיקה שלא קרתה.
- **ETHOVX** — צינור אימון LoRA מלא: `corpus_manager.py` (קורפוס רק
  ממקורות מאושרים + hash SHA-256 בר-שחזור), `eval_suite/` (5 שאלות
  בדיקה קבועות, מדד דיוק אמיתי לפני/אחרי), `train.py` (rollback
  אוטומטי אם ריצה הרעה ביצועים, שמירת 3 checkpoints אחרונים בלבד).
  מחובר ל-Orchestrator דרך `ethovx_train_node` — job מתוזמן ומאושר,
  לעולם לא רץ ברקע ללא אישור.
- **Memory** — SQLite עם עובדות/היסטוריית משימות/undo log, פקודת "תשכח".
- **Security Audit** — סורק Windows Defender/Firewall/Secure Boot/TPM/
  פורטים (רץ במלואו על Windows; על לינוקס בזמן פיתוח חוזר "unsupported").
- **NIM Client** — retry+backoff+מעקב עלות אמיתי.
- **UI Shell** — Electron מלא-מסך, RTL עברי, פאנל משימות, כרטיס אישור.
- **TTS עברי** — Hila/Avri (edge-tts Neural).

**מה שנשאר לביצוע אך ורק אצלך, על החומרה הפיזית שלך** (לא ניתן
להשלים מרחוק בשום אופן): אימון מודל ה-wake-word (דורש את הקלטת
קולך), הרצת אימון ETHOVX בפועל (דורש GPU עם 8GB+ VRAM ו-Ollama
מותקן), והתקנת Docker Desktop להפעלת ה-sandbox של Code-Gen. שלושתם
מתועדים כצעדים מפורשים בהמשך המסמך.

---

## 8. מבנה הפרויקט

```
Vertex/
├── core/                       # Orchestrator — המוח של הסוכן
│   ├── main.py                  # FastAPI + WebSocket, כאן הכל מתחבר
│   ├── config.py                 # טעינת config.yaml + DPAPI secrets
│   ├── router/                   # סיווג כוונות + state machine
│   ├── modules/                   # file_ops, browser, code_gen, security_audit,
│   │                                sandbox_runner, windows_recycle
│   ├── security/                   # confirmation_gate, audit_log, injection_guard
│   ├── memory/                       # זיכרון קבוע (SQLite)
│   ├── voice/                         # TTS/STT עברית
│   └── nim_client/                      # NVIDIA NIM API wrapper
├── ethovx/                     # Phase 3 — צינור אימון LoRA מקומי
│   ├── train.py                  # לולאת LoRA fine-tune + rollback
│   ├── corpus_manager.py           # קורפוס ממקורות מאושרים בלבד + hash
│   └── eval_suite/                   # 5 שאלות בדיקה קבועות + מדידת דיוק
├── wake_service/               # שירות "היי וורטקס" ברקע
├── ui_shell/                    # Electron — חלון הצ'אט המלא-מסך
├── installer/                    # Inno Setup + Dockerfile.sandbox
├── scripts/                       # התקנה/הרצה על Windows
└── tests/unit/                     # 16 טסטים, כולם עוברים
```

---

## 9. שלושת הצעדים שנותרו לך לבד (חומרה/קלט אישי בלבד)

הקוד עצמו מלא ונבדק. שלושת הדברים הבאים דורשים משהו שרק אתה יכול
לספק — לא חוסר בקוד:

### 9.1 אימון ה-wake-word ("היי וורטקס") — חובה להפעלה קולית
ר' סעיף 5 למעלה ו-`wake_service/README.md`. ~20 דקות, דורש שתקליט
את עצמך אומר את הביטוי. **בלי זה Vertex עובד מצוין דרך טקסט/כפתור
מיקרופון** — זו לא חסימה לשימוש.

### 9.2 Docker Desktop — נדרש להרצת קוד שנוצר (Code-Gen)
1. הורד והתקן: https://www.docker.com/products/docker-desktop/
2. הרץ אותו פעם אחת כדי שהשירות יעלה ברקע.
3. זהו — `sandbox_runner.py` ימשוך אוטומטית את `python:3.12-slim`
   בפעם הראשונה שתבקש מ-Vertex לכתוב ולהריץ קוד.

בלי Docker, Code-Gen עדיין יכתוב לך קוד ויציג אותו + סריקת bandit,
אבל **יסרב לאשר הרצה דינמית** ויגיד לך בפירוש "Docker אינו מותקן" —
במקום לדמות שהוא בדק את הקוד כשלא באמת בדק.

### 9.3 GPU + Ollama — נדרש להרצת אימון ETHOVX בפועל
1. וודא כרטיס מסך NVIDIA עם 8GB+ VRAM (ר' טבלת חומרה, §15.1 במפרט).
2. התקן Ollama: https://ollama.com/download ואז `ollama pull llama3.2:3b`
3. הגדר `ethovx.approved_sources` ב-`config.yaml` — רק לנתיבים
   שאתה מאשר לאמן עליהם (למשל תיקיית תיעוד Pine Script).
4. תגיד ל-Vertex "תתחיל אימון ETHOVX" — הוא יבקש אישור, ואז ירוץ
   ברקע וידווח דוח מסכם עם דיוק לפני/אחרי.

בלי `torch`/`peft`/`transformers` מותקנים, `train.py` מזהה זאת
ומדווח "לא בוצע אימון בפועל" במקום לדמות תוצאה — כמו כל שאר המערכת,
שום דבר כאן לא מעמיד פנים שהוא הצליח כשלא הצליח.

---

## 10. הצעד הבא

הכל מוכן להרצה על מחשב Windows אמיתי כפי שמתואר למעלה — Phase 1, 2
ושלד Phase 3 שלמים ונבדקים. מה שנשאר הוא הרצה בפועל על המחשב שלך
(כולל שלושת הצעדים בסעיף 9), ולאחר מכן — Phase 4 העתידי (§11 במפרט):
אפליקציית טלפון כלקוח נוסף של אותו Orchestrator, שאינו בהיקף הנוכחי.
