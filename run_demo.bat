@echo off
title Ever Recover - Demo Mode

REM Check if venv exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Run demo
python ever_recover.py --demo
pause