@echo off
cd /d "%~dp0"
echo Setting up Smart City Project Environment...

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH. Please install Python 3.
    pause
    exit /b
)

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
) else (
    echo Virtual environment already exists.
)

REM Install dependencies
echo Installing dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install cryptography

echo.
echo Setup Complete!
echo You can now run the project using 'run_venv.bat'
pause
