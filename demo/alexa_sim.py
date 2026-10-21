"""Alexa+ Voice Simulator CLI.

Simulates an Alexa+ conversational agent interacting with the HomeGuard MCP server.
Maps natural spoken phrases to official MCP tool calls and renders the voice 'spoken' output.

Usage:
    python demo/alexa_sim.py [--url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
import urllib.request
import urllib.error


class AlexaSimulator:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.current_incident_id: str | None = None
        self.last_proposed_incident: str | None = None

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send POST request to HomeGuard server."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"error": f"Failed to connect to HomeGuard server at {self.base_url}: {e}"}

    def _get(self, endpoint: str) -> dict[str, Any]:
        """Send GET request to HomeGuard server."""
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"error": f"Failed to connect to HomeGuard server at {self.base_url}: {e}"}

    def print_alexa(self, text: str, tool_info: str | None = None) -> None:
        """Pretty-print Alexa's spoken reply."""
        if tool_info:
            print(f"\n\033[90m⚙️ [MCP Tool Call] {tool_info}\033[0m")
        print(f"\033[1;36mAlexa+ 🗣️ : \033[0m\033[1;37m\"{text}\"\033[0m\n")

    def print_system(self, text: str) -> None:
        print(f"\033[93m[System] {text}\033[0m")

    def handle_status(self) -> None:
        res = self._get("/api/status")
        if "error" in res:
            self.print_alexa(f"I cannot reach the HomeGuard server. {res['error']}")
            return
        diag = res.get("diagnosis", {})
        devices = res.get("devices", {})
        unhealthy = [d for d in devices.values() if d.get("status") != "online"]
        if not unhealthy:
            spoken = "All 5 simulated devices in your home are online and working normally."
        else:
            names = [d["name"].replace(" (Simulated)", "") for d in unhealthy]
            spoken = f"Your simulated {', '.join(names)} are experiencing connection issues."
        self.print_alexa(spoken, "home_status()")

    def handle_diagnose_and_propose(self) -> None:
        # Step 1: Diagnose
        status_res = self._get("/api/status")
        if "error" in status_res:
            self.print_alexa(f"Could not connect to HomeGuard. {status_res['error']}")
            return

        diag = status_res.get("diagnosis", {})
        if not diag.get("has_incident"):
            self.print_alexa(
                "I checked your home network. Everything is running smoothly and all simulated devices are online.",
                "diagnose_home() -> Healthy",
            )
            return

        diag_spoken = diag.get("spoken", "")

        # Step 2: Propose Fix
        prop_res = self._post("/api/propose_fix", {})
        self.current_incident_id = prop_res.get("incident_id")
        self.last_proposed_incident = self.current_incident_id
        prop_spoken = prop_res.get("spoken", "")

        combined_spoken = f"{diag_spoken} {prop_spoken}"
        self.print_alexa(
            combined_spoken,
            f"diagnose_home() & propose_fix(incident_id='{self.current_incident_id}')",
        )

    def handle_approve(self, confirmed: bool) -> None:
        if not self.current_incident_id:
            # Check if there is an active incident on the server
            status_res = self._get("/api/status")
            incidents = status_res.get("incidents", {})
            if incidents:
                self.current_incident_id = list(incidents.keys())[-1]
            else:
                self.print_alexa(
                    "There are no pending fixes to approve. Ask me 'what's wrong with my home' first.",
                    "approve_fix() -> Refused (No Incident)",
                )
                return

        appr_res = self._post(
            "/api/approve_fix",
            {"incident_id": self.current_incident_id, "user_confirmed": confirmed},
        )
        if not confirmed:
            self.print_alexa(
                appr_res.get("spoken", "Cancelled the fix."),
                f"approve_fix(incident_id='{self.current_incident_id}', user_confirmed=False)",
            )
            return

        if not appr_res.get("executed"):
            self.print_alexa(
                appr_res.get("spoken", "I could not execute the fix."),
                f"approve_fix(incident_id='{self.current_incident_id}') -> Refused",
            )
            return

        # Executed! Now immediately follow up with verification check
        exec_spoken = appr_res.get("spoken", "")
        print(f"\033[90m⚙️ [MCP Tool Call] approve_fix('{self.current_incident_id}', user_confirmed=True)\033[0m")
        print(f"\033[1;36mAlexa+ 🗣️ : \033[0m\033[1;37m\"{exec_spoken}\"\033[0m")
        time.sleep(1.2)

        # Run verification check
        ver_res = self._post("/api/verify_fix", {"incident_id": self.current_incident_id})
        ver_spoken = ver_res.get("spoken", "")
        self.print_alexa(
            ver_spoken,
            f"verify_fix(incident_id='{self.current_incident_id}', ticks=3)",
        )

    def handle_rollback(self) -> None:
        if not self.current_incident_id:
            status_res = self._get("/api/status")
            incidents = status_res.get("incidents", {})
            if incidents:
                self.current_incident_id = list(incidents.keys())[-1]
            else:
                self.print_alexa("There is no recent fix to undo.")
                return

        rb_res = self._post("/api/rollback_fix", {"incident_id": self.current_incident_id})
        self.print_alexa(
            rb_res.get("spoken", "Restored previous state."),
            f"rollback_fix(incident_id='{self.current_incident_id}')",
        )

    def handle_inject(self, flaky: bool = False) -> None:
        mode_desc = "flaky extender (fails verification demo)" if flaky else "standard extender outage"
        self.print_system(f"Simulating outage: {mode_desc}...")
        res = self._post(
            "/api/inject_failure",
            {"device_id": "wifi_extender", "mode": "offline", "fail_verification": flaky},
        )
        self.print_system("Failure injected! Check dashboard at http://127.0.0.1:8000/")

    def handle_clear(self) -> None:
        self.print_system("Clearing all outages and resetting devices...")
        self._post("/api/clear_failures", {})
        self.current_incident_id = None
        self.print_system("All devices restored to online!")

    def dispatch(self, user_input: str) -> bool:
        phrase = user_input.strip().lower()
        if not phrase:
            return True

        if phrase in {"exit", "quit", "q", "bye"}:
            print("\nGoodbye from Alexa+ & HomeGuard!\n")
            return False

        if phrase in {"help", "?"}:
            print("\n\033[1mSupported Natural Phrases for Demo:\033[0m")
            print("  - 'what's wrong with my home' (or 'diagnose', 'why is my fire tv buffering')")
            print("  - 'yes go ahead' (or 'yes', 'confirm', 'do it')")
            print("  - 'no don't do it' (or 'no', 'cancel')")
            print("  - 'undo that' (or 'rollback', 'revert')")
            print("  - 'what's the status' (or 'how is my home', 'status')")
            print("  - 'inject failure' (simulates Wi-Fi Extender drop)")
            print("  - 'inject flaky' (simulates self-checking failure verification & auto-rollback)")
            print("  - 'clear' (clears all simulated failures)")
            print("  - 'exit' (quits the simulator)\n")
            return True

        # Mapping natural language to tools
        if any(kw in phrase for kw in ["wrong", "diagnose", "broken", "buffering", "problem", "issue", "troubleshoot"]):
            self.handle_diagnose_and_propose()
        elif any(kw in phrase for kw in ["no", "don't", "dont", "cancel", "stop", "abort"]):
            self.handle_approve(confirmed=False)
        elif any(kw in phrase for kw in ["yes", "go ahead", "confirm", "restart", "do it", "sure", "proceed", "approve"]):
            self.handle_approve(confirmed=True)
        elif any(kw in phrase for kw in ["undo", "rollback", "revert"]):
            self.handle_rollback()
        elif any(kw in phrase for kw in ["status", "how is", "all good", "healthy", "check"]):
            self.handle_status()
        elif "inject flaky" in phrase:
            self.handle_inject(flaky=True)
        elif "inject" in phrase or "break" in phrase or "fail" in phrase:
            self.handle_inject(flaky=False)
        elif "clear" in phrase or "reset" in phrase:
            self.handle_clear()
        else:
            self.print_alexa(
                f"I'm not sure how to help with '{user_input}'. You can ask 'what's wrong with my home' or type 'help'.",
                None,
            )
        return True

    def run_interactive(self) -> None:
        print("\n" + "=" * 65)
        print("  \033[1;36mAlexa+ Smart Home Voice Simulator (HomeGuard Demo)\033[0m")
        print("  Connected to: " + self.base_url)
        print("  Type natural voice commands or 'help' for phrases. 'exit' to quit.")
        print("=" * 65 + "\n")

        # Check server connection
        status_res = self._get("/api/status")
        if "error" in status_res:
            print(f"\033[91m⚠️ Warning: HomeGuard server not responding at {self.base_url}\033[0m")
            print("\033[93mPlease run the server first: python -m homeguard.dashboard\033[0m\n")

        while True:
            try:
                user_input = input("\033[1;32mYou 🎤 > \033[0m")
                if not self.dispatch(user_input):
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Alexa+ Simulator for HomeGuard Demo")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="HomeGuard server URL")
    args = parser.parse_args()
    sim = AlexaSimulator(base_url=args.url)
    sim.run_interactive()


if __name__ == "__main__":
    main()
