@echo off
title Ever Recover - GUI Mode

REM Check if venv exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Run GUI
python ever_recover.py
if errorlevel 1 (
    echo.
    echo Ever Recover exited with an error.
    pause
)