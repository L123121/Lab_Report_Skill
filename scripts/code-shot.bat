@echo off
REM code-shot.bat - Windows batch wrapper for code_shot.py
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."
if exist "%REPO_DIR%\.venv\Scripts\python.exe" (
    "%REPO_DIR%\.venv\Scripts\python.exe" "%SCRIPT_DIR%code_shot.py" %*
) else (
    python "%SCRIPT_DIR%code_shot.py" %*
)
