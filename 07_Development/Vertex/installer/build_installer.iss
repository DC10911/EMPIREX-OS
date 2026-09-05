; Vertex — Inno Setup installer script (מפרט §23.1).
; דורש Inno Setup (https://jrsoftware.org/isinfo.php) על מכונת build של Windows.
; לפני קימפול: יש לבנות תחילה את core (PyInstaller) ו-ui_shell (electron-builder)
; לתוך dist\core ו-dist\ui_shell.

[Setup]
AppName=Vertex
AppVersion=1.0.0
DefaultDirName={autopf}\Vertex
DefaultGroupName=Vertex
OutputBaseFilename=VertexSetup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
SignTool=signtool

[Files]
Source: "dist\core\*"; DestDir: "{app}\core"; Flags: recursesubdirs
Source: "dist\ui_shell\*"; DestDir: "{app}\ui"; Flags: recursesubdirs
Source: "dist\wake_service\*"; DestDir: "{app}\wake"; Flags: recursesubdirs

[Icons]
; קיצור דרך יחיד בשולחן העבודה + בתפריט התחל — לא פותח תיקיית התקנה
Name: "{autodesktop}\Vertex"; Filename: "{app}\ui\Vertex.exe"
Name: "{autoprograms}\Vertex"; Filename: "{app}\ui\Vertex.exe"

[Run]
Filename: "{app}\wake\wake_service.exe"; Flags: runhidden nowait; \
    Description: "התקנת שירות רקע"
; רישום כ-Startup Task ולא כתהליך שדורש פתיחה ידנית
Filename: "schtasks.exe"; Parameters: "/create /tn ""Vertex Wake Service"" /tr ""{app}\wake\wake_service.exe"" /sc onlogon /rl limited"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
