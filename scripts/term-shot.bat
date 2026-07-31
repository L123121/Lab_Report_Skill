@echo off
REM term-shot.bat - Windows batch wrapper for term_shot.py
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."
if exist "%REPO_DIR%\.venv\Scripts\python.exe" (
    "%REPO_DIR%\.venv\Scripts\python.exe" "%SCRIPT_DIR%term_shot.py" %*
) else (
    python "%SCRIPT_DIR%term_shot.py" %*
)
