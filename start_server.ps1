# EMPIREX Server Launcher — detached from terminal so it survives terminal close
# Usage: Right-click → "Run with PowerShell"  OR  just double-click

$PYTHON = "c:\Users\danie\Documents\EMPIREX_OS\.venv\Scripts\python.exe"
$SCRIPT = "$PSScriptRoot\empirex_server.py"
$LOG    = "$PSScriptRoot\server.log"

Write-Host "=== EMPIREX SERVER ===" -ForegroundColor Cyan

# Kill any running instance
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'empirex_server' }
if ($procs) {
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped old server process(es)." -ForegroundColor Yellow
    Start-Sleep -Milliseconds 800
}

# Launch detached — survives terminal close
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName  = $PYTHON
$psi.Arguments = "`"$SCRIPT`""
$psi.WorkingDirectory = $PSScriptRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow  = $false
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError  = $false

$proc = [System.Diagnostics.Process]::Start($psi)
Write-Host "Server started (PID $($proc.Id)) at http://localhost:5501" -ForegroundColor Green
Write-Host "Close this window safely — server keeps running." -ForegroundColor DarkGray
