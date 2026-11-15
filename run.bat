@echo off
REM =========================================================================
REM SellerOps Control Tower - Windows Local Launcher (Portable)
REM =========================================================================

cd /d "%~dp0"

echo [1/3] Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python 3.8+.
    pause
    exit /b 1
)

echo [2/3] Checking database status...
if not exist "data\sellerops.db" (
    echo [*] Database not found. Generating starter demo dataset with seed 20261022...
    python src\generator.py --scale demo
) else (
    echo [✓] Database found at data\sellerops.db.
)

echo [3/3] Starting SellerOps Control Tower HTTP Server...
echo =========================================================================
echo Operations Dashboard: http://127.0.0.1:8000/
echo REST API Endpoints:  http://127.0.0.1:8000/api/summary
echo Press Ctrl+C in this console to stop the server.
echo =========================================================================

python src\server.py
pause
