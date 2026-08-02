@echo off
setlocal
rem cd to script dir; "%~dp0." avoids trailing-backslash quote escaping
cd /d "%~dp0."

where uv >nul 2>nul
if errorlevel 1 (
    echo [rp-agent] uv not found. Install with: winget install --id=astral-sh.uv -e
    pause
    exit /b 1
)

uv sync >nul
if "%~1"=="" (
    uv run rp-agent shell
) else (
    uv run rp-agent %*
)
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
