#!/usr/bin/env bash
# ==============================================================================
# HomeGuard Demo Runner Script
# Amazon "Build, Ship, Shape" Hackathon - Alexa+ Track
# ==============================================================================

set -e

echo "======================================================================"
echo "🛡️  Starting HomeGuard: The Smart Home That Explains Itself"
echo "======================================================================"
echo ""
echo "Note: ALL devices are SIMULATED. No real smart home hardware is called."
echo ""

# Find python interpreter
if [ -d ".venv" ]; then
    if [ -f ".venv/bin/python" ]; then
        PYTHON=".venv/bin/python"
    elif [ -f ".venv/Scripts/python.exe" ]; then
        PYTHON=".venv/Scripts/python.exe"
    else
        PYTHON="python"
    fi
else
    PYTHON="python"
fi

echo "Using Python: $PYTHON"
echo ""

# Start the combined server (FastAPI Dashboard + MCP Server) in the background
echo "Starting HomeGuard server on http://127.0.0.1:8000..."
$PYTHON -m homeguard.dashboard &
SERVER_PID=$!

# Ensure server cleanup on exit
cleanup() {
    echo ""
    echo "Stopping HomeGuard server (PID $SERVER_PID)..."
    kill $SERVER_PID 2>/dev/null || true
    echo "Shutdown complete. Goodbye!"
}
trap cleanup EXIT INT TERM

# Wait for server to initialize
sleep 2

echo ""
echo "======================================================================"
echo "🎯 DEMO WALKTHROUGH - EXACT PHRASES TO SAY TO ALEXA+"
echo "======================================================================"
echo ""
echo "1. Open the live dashboard in your browser:"
echo "   👉 http://127.0.0.1:8000/"
echo ""
echo "2. Inject a simulated failure (either click the button on the dashboard"
echo "   or type 'inject failure' in the CLI prompt below)."
echo "   Watch the Wi-Fi Extender turn RED, Ring Doorbell OFFLINE, Fire TV BUFFERING."
echo ""
echo "3. Say: 'what's wrong with my home'"
echo "   -> Alexa+ runs root cause analysis, identifies the Wi-Fi Extender as the"
echo "      single root cause, explains the impact of restarting it, and asks for confirmation."
echo ""
echo "4. Say: 'yes go ahead'"
echo "   -> Alexa+ safely executes restart, runs 3-tick stabilization checks,"
echo "      and confirms that all 4 affected devices are recovered."
echo ""
echo "5. (Optional Self-Check Demo) Type: 'inject flaky'"
echo "   -> Injects an extender fault that fails stabilization."
echo "   -> Say: 'what's wrong with my home' then 'yes go ahead'"
echo "   -> Alexa+ restarts, fails verification on tick 2, and automatically"
echo "      rolls back to previous state to prevent a half-broken setup!"
echo ""
echo "6. Say: 'undo that' at any time to demonstrate instant rollback."
echo ""
echo "======================================================================"
echo "Launching Alexa+ Voice Simulator CLI..."
echo "======================================================================"

$PYTHON demo/alexa_sim.py --url http://127.0.0.1:8000
