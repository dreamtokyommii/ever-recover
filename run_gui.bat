@echo off
title Ever Recover - GUI Mode

REM Always run from the folder this file lives in (needed for "Run as administrator")
cd /d "%~dp0"

REM Use the project's virtual environment if it exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python ever_recover.py
if errorlevel 1 (
    echo.
    echo Ever Recover exited with an error.
    pause
)