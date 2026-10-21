@echo off
REM ==============================================================================
REM HomeGuard Demo Runner Script (Windows CMD / PowerShell companion)
REM Amazon "Build, Ship, Shape" Hackathon - Alexa+ Track
REM ==============================================================================

echo ======================================================================
echo 🛡️  Starting HomeGuard: The Smart Home That Explains Itself
echo ======================================================================
echo.
echo Note: ALL devices are SIMULATED. No real smart home hardware is called.
echo.

set PYTHON=.venv\Scripts\python.exe
if not exist %PYTHON% (
    set PYTHON=python
)

echo Starting HomeGuard Server (FastAPI + MCP Server)...
start /B "" %PYTHON% -m homeguard.dashboard

echo Waiting 2 seconds for server startup...
timeout /t 2 /nobreak >nul

echo.
echo ======================================================================
echo 🎯 DEMO WALKTHROUGH - EXACT PHRASES TO SAY TO ALEXA+
echo ======================================================================
echo.
echo 1. Open the live dashboard in your browser:
echo    👉 http://127.0.0.1:8000/
echo.
echo 2. Say: "what's wrong with my home"
echo 3. Say: "yes go ahead"
echo 4. Say: "inject flaky" then "what's wrong with my home" then "yes go ahead"
echo 5. Say: "undo that"
echo.
echo ======================================================================
echo Launching Alexa+ Voice Simulator CLI...
echo ======================================================================

%PYTHON% demo\alexa_sim.py --url http://127.0.0.1:8000
