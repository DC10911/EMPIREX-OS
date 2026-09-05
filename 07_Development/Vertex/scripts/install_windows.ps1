<#
.SYNOPSIS
    התקנת Vertex למחשב Windows — מסלול פיתוח/הרצה ישירה (ללא בניית installer חתום).

.DESCRIPTION
    סקריפט זה הוא הדרך המהירה להריץ את Vertex על המחשב שלך *עכשיו*, לפני
    שנבנה installer.exe חתום דיגיטלית (§23.1) לגרסת ההפצה הסופית. הוא:
      1. יוצר את תיקיית ההתקנה C:\Vertex (או נתיב מותאם).
      2. מעתיק את כל קבצי הפרויקט לתיקייה הזו.
      3. יוצר סביבת Python וירטואלית ומתקין תלויות.
      4. מתקין את תלויות ה-UI (npm install).
      5. יוצר קיצורי דרך על שולחן העבודה ובתפריט התחל.
      6. רושם את שירות ה-Wake Word כ-Scheduled Task שרץ בכניסה למשתמש.

    יש להריץ מתוך PowerShell רגיל (לא חובה כ-Administrator — §10: Vertex
    רץ כמשתמש רגיל כברירת מחדל).

.PARAMETER InstallDir
    נתיב היעד להתקנה. ברירת מחדל: C:\Vertex
#>

param(
    [string]$InstallDir = "C:\Vertex",
    [string]$SourceDir = (Split-Path -Parent $PSScriptRoot)
)

Write-Host "=== התקנת Vertex ===" -ForegroundColor Cyan
Write-Host "מקור:  $SourceDir"
Write-Host "יעד:   $InstallDir"
Write-Host ""

# 1. יצירת תיקיית היעד
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 2. העתקת קבצי הפרויקט (למעט venv/node_modules אם קיימים כבר)
Write-Host "מעתיק קבצים ל-$InstallDir ..."
robocopy $SourceDir $InstallDir /E /XD ".git" "venv" "node_modules" "__pycache__" "tts_cache" | Out-Null

# 3. סביבת Python + תלויות
Write-Host "מגדיר סביבת Python..."
Push-Location $InstallDir
python -m venv venv
& "$InstallDir\venv\Scripts\pip.exe" install --upgrade pip
& "$InstallDir\venv\Scripts\pip.exe" install -r requirements.txt

# 4. תלויות UI
Write-Host "מתקין תלויות ממשק (npm)..."
Push-Location "$InstallDir\ui_shell"
npm install
Pop-Location

# 5. קובץ config.yaml ראשוני
if (-not (Test-Path "$InstallDir\config.yaml")) {
    Copy-Item "$InstallDir\config.yaml.example" "$InstallDir\config.yaml"
    (Get-Content "$InstallDir\config.yaml") -replace 'install_dir:.*', "install_dir: `"$InstallDir`"" |
        Set-Content "$InstallDir\config.yaml"
}

# 6. קיצורי דרך
Write-Host "יוצר קיצורי דרך..."
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Vertex.lnk")
$Shortcut.TargetPath = "$InstallDir\scripts\start_vertex.bat"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "Vertex — סוכן AI אישי מקומי"
$Shortcut.Save()

# 7. Scheduled Task לשירות ה-Wake Word (רק אם המודל המאומן כבר קיים)
$wakeModel = "$InstallDir\wake_service\models\hey_vertex.onnx"
if (Test-Path $wakeModel) {
    schtasks /create /tn "Vertex Wake Service" `
        /tr "$InstallDir\venv\Scripts\pythonw.exe $InstallDir\wake_service\listener.py" `
        /sc onlogon /rl limited /f
    Write-Host "שירות Wake Word נרשם להפעלה אוטומטית בכניסה למשתמש." -ForegroundColor Green
} else {
    Write-Host "שים לב: מודל ה-wake-word עדיין לא אומן." -ForegroundColor Yellow
    Write-Host "הרץ קודם: python wake_service\record_samples.py --label positive --count 50" -ForegroundColor Yellow
    Write-Host "ר' wake_service\README.md לפרטים מלאים." -ForegroundColor Yellow
}

Pop-Location

Write-Host ""
Write-Host "=== ההתקנה הושלמה ===" -ForegroundColor Green
Write-Host "1. פתח את $InstallDir\config.yaml והגדר את מפתח ה-NVIDIA NIM API (ר' README.md)."
Write-Host "2. הפעל את Vertex דרך קיצור הדרך על שולחן העבודה, או ע"י:"
Write-Host "   $InstallDir\scripts\start_vertex.bat"
