@echo off
echo ========================================
echo Building Ever Recover for Windows
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    exit /b 1
)

echo [1/5] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    exit /b 1
)

echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/5] Upgrading pip...
python -m pip install --upgrade pip

echo [4/5] Installing dependencies...
python -m pip install PyQt6 reportlab numpy tqdm psutil pytest

echo [5/5] Verifying installation...
python -c "import PyQt6; import reportlab; import numpy; print('All dependencies installed successfully!')"

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo To run Ever Recover:
echo   1. Activate venv: .venv\Scripts\Activate.ps1
echo   2. Run: python ever_recover.py
echo.
echo Or use the convenience scripts:
echo   - run_gui.bat (GUI mode)
echo   - run_demo.bat (Demo mode)
echo   - run_cli.bat (CLI mode)
echo.
pause