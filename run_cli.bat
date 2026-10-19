@echo off
title Ever Recover - CLI Mode

REM Check if venv exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Show CLI help
python ever_recover.py --help