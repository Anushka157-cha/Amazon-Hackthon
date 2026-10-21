"""End-to-End Automated Demo Runner.

Runs through the complete user experience against the running HomeGuard server.
"""

import sys
import time
from pathlib import Path

# Fix Windows console Unicode encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.alexa_sim import AlexaSimulator

def run_e2e_demo():
    sim = AlexaSimulator("http://127.0.0.1:8000")

    print("\n" + "=" * 70)
    print("🚀 DEMO STEP 1: Check Home Health Status (Baseline)")
    print("=" * 70)
    sim.dispatch("status")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("💥 DEMO STEP 2: Inject Simulated Wi-Fi Extender Outage")
    print("=" * 70)
    sim.dispatch("inject failure")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("🎙️ DEMO STEP 3: User Asks: \"what's wrong with my home\"")
    print("=" * 70)
    sim.dispatch("what's wrong with my home")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("✅ DEMO STEP 4: User Confirms: \"yes go ahead\"")
    print("=" * 70)
    sim.dispatch("yes go ahead")
    time.sleep(1.5)

    print("\n" + "=" * 70)
    print("⚠️ DEMO STEP 5: Inject Flaky Extender (Self-Checking Failure Test)")
    print("=" * 70)
    sim.dispatch("inject flaky")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("🎙️ DEMO STEP 6: Ask & Confirm Fix on Flaky Device")
    print("=" * 70)
    sim.dispatch("what's wrong with my home")
    time.sleep(1)
    sim.dispatch("yes go ahead")
    time.sleep(1.5)

    print("\n" + "=" * 70)
    print("↩️ DEMO STEP 7: Test Rollback Command (\"undo that\")")
    print("=" * 70)
    sim.dispatch("undo that")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("✨ DEMO STEP 8: Clear All Outages & Reset Home")
    print("=" * 70)
    sim.dispatch("clear")

    print("\n" + "=" * 70)
    print("🎯 All Demo Steps Successfully Executed Live!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_e2e_demo()
