@echo off
REM start_demo.bat — Start backend + dashboard for live demo
REM Run this from the repo root:  demo\start_demo.bat
REM
REM Opens two new Command Prompt windows:
REM   Window 1: uvicorn backend on port 8000
REM   Window 2: Python HTTP server for dashboard on port 8080
REM
REM After both windows show "ready", open:
REM   http://127.0.0.1:8080   (dashboard)
REM   http://127.0.0.1:8000   (backend API docs)

echo.
echo ===================================================
echo  Industrial Safety Monitoring System - Demo Start
echo ===================================================
echo.

REM Change to repo root (one level up from demo/)
cd /d "%~dp0.."

REM Check venv exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found at venv\Scripts\python.exe
    echo Run this from the repo root and ensure venv is set up.
    pause
    exit /b 1
)

echo [1/2] Starting backend on http://127.0.0.1:8000 ...
start "Backend - uvicorn" cmd /k "venv\Scripts\activate && uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000"

REM Give the backend a moment to start before opening the dashboard
timeout /t 3 /nobreak > nul

echo [2/2] Starting dashboard on http://127.0.0.1:8080 ...
start "Dashboard - HTTP server" cmd /k "venv\Scripts\activate && python -m http.server 8080 --directory dashboard"

echo.
echo ===================================================
echo  Both services starting in separate windows.
echo.
echo  Wait for "Application startup complete" in the
echo  Backend window, then open:
echo.
echo    Dashboard : http://127.0.0.1:8080
echo    API docs  : http://127.0.0.1:8000/docs
echo    Health    : http://127.0.0.1:8000/health
echo.
echo  To inject demo events (after backend is ready):
echo    venv\Scripts\python demo\demo_inject_events.py
echo ===================================================
echo.
pause
