@echo off
setlocal

rem First run: relaunch self minimized, then exit (double-click experience)
if "%1"=="--minimized" goto :main
start "" /min cmd /c "%~f0" --minimized
exit /b

:main
rem cd to script dir; "%~dp0." avoids trailing-backslash quote escaping
cd /d "%~dp0."

where uv >nul 2>nul
if errorlevel 1 (
    echo [rp-agent] uv not found. Install with: winget install --id=astral-sh.uv -e
    pause
    exit /b 1
)

rem Launch PowerShell (normal window) running rp-agent shell; this window ends
start "" powershell -NoExit -Command "Set-Location '%~dp0.'; uv sync; uv run rp-agent shell"
exit /b 0
