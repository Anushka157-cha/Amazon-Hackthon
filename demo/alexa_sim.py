"""Alexa+ Voice Simulator CLI.

Simulates an Alexa+ conversational agent interacting with the HomeGuard MCP server.
Calls official MCP tools over Streamable-HTTP transport using the MCP Python SDK client,
and renders natural voice 'spoken' outputs.

Usage:
    python demo/alexa_sim.py [--url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any
import urllib.error
import urllib.request

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Fix Windows console Unicode encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


class AlexaSimulator:
    """Alexa+ conversational voice simulator powered by MCP Streamable-HTTP tools."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.mcp_url = f"{self.base_url}/mcp"
        self.current_incident_id: str | None = None
        self.last_proposed_incident: str | None = None

    async def _async_call_mcp_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call an MCP tool over Streamable-HTTP transport."""
        arguments = arguments or {}
        try:
            async with streamable_http_client(self.mcp_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(tool_name, arguments)
                    if res.is_error:
                        return {"error": "TOOL_ERROR", "message": f"MCP tool '{tool_name}' reported an error."}
                    if res.content and hasattr(res.content[0], "text"):
                        return json.loads(res.content[0].text)
                    return {}
        except Exception as e:
            return {
                "error": "MCP_CONNECTION_ERROR",
                "message": f"Failed to call MCP tool '{tool_name}' at {self.mcp_url}: {e}",
            }

    def call_mcp_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous wrapper for MCP Streamable-HTTP tool calls."""
        return asyncio.run(self._async_call_mcp_tool(tool_name, arguments))

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send POST request to HomeGuard control API (used for test fault injection)."""
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
        """Send GET request to HomeGuard control API."""
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
            print(f"\n\033[90m⚙️ [MCP Streamable-HTTP Tool Call] {tool_info}\033[0m")
        print(f"\033[1;36mAlexa+ 🗣️ : \033[0m\033[1;37m\"{text}\"\033[0m\n")

    def print_system(self, text: str) -> None:
        print(f"\033[93m[System] {text}\033[0m")

    def handle_status(self) -> None:
        """Query home status using the official MCP tool home_status()."""
        data = self.call_mcp_tool("home_status", {})
        if "error" in data:
            self.print_alexa(
                f"I cannot reach the HomeGuard MCP server at {self.mcp_url}. {data.get('message', '')}"
            )
            return

        spoken = data.get("spoken", "All devices are online.")
        self.print_alexa(spoken, "home_status()")

    def handle_diagnose_and_propose(self) -> None:
        """Perform RCA via MCP diagnose_home() and propose safe fix via propose_fix()."""
        # Step 1: Diagnose
        diag = self.call_mcp_tool("diagnose_home", {})
        if "error" in diag:
            self.print_alexa(
                f"Could not reach HomeGuard MCP server: {diag.get('message', '')}"
            )
            return

        if not diag.get("has_incident"):
            self.print_alexa(
                diag.get(
                    "spoken",
                    "I checked your home network. Everything is running smoothly and all simulated devices are online.",
                ),
                "diagnose_home() -> Healthy",
            )
            return

        diag_spoken = diag.get("spoken", "")

        # Step 2: Propose Fix
        prop = self.call_mcp_tool("propose_fix", {})
        if "error" in prop:
            self.print_alexa(f"Failed to propose fix: {prop.get('message', '')}")
            return

        self.current_incident_id = prop.get("incident_id")
        self.last_proposed_incident = self.current_incident_id
        prop_spoken = prop.get("spoken", "")

        combined_spoken = f"{diag_spoken} {prop_spoken}".strip()
        self.print_alexa(
            combined_spoken,
            f"diagnose_home() & propose_fix(incident_id='{self.current_incident_id}')",
        )

    def handle_approve(self, confirmed: bool) -> None:
        """Confirm or reject fix via MCP approve_fix(), then verify via verify_fix()."""
        if not self.current_incident_id:
            diag = self.call_mcp_tool("diagnose_home", {})
            if diag.get("has_incident"):
                prop = self.call_mcp_tool("propose_fix", {})
                self.current_incident_id = prop.get("incident_id")
            else:
                self.print_alexa(
                    "There are no pending fixes to approve. Ask me 'what's wrong with my home' first.",
                    "approve_fix() -> Refused (No Incident)",
                )
                return

        appr_res = self.call_mcp_tool(
            "approve_fix",
            {"incident_id": self.current_incident_id, "user_confirmed": confirmed},
        )
        if "error" in appr_res:
            self.print_alexa(f"Error during approval: {appr_res.get('message')}")
            return

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

        # Executed! Now print execution response
        exec_spoken = appr_res.get("spoken", "")
        print(f"\033[90m⚙️ [MCP Streamable-HTTP Tool Call] approve_fix('{self.current_incident_id}', user_confirmed=True)\033[0m")
        print(f"\033[1;36mAlexa+ 🗣️ : \033[0m\033[1;37m\"{exec_spoken}\"\033[0m")
        time.sleep(1.0)

        # Step 3: Verify Fix across 3 ticks via MCP verify_fix
        ver_res = self.call_mcp_tool("verify_fix", {"incident_id": self.current_incident_id})
        ver_spoken = ver_res.get("spoken", "Stabilization check complete.")
        self.print_alexa(
            ver_spoken,
            f"verify_fix(incident_id='{self.current_incident_id}', ticks=3)",
        )

    def handle_rollback(self) -> None:
        """Rollback fix via MCP rollback_fix()."""
        if not self.current_incident_id:
            status_res = self._get("/api/status")
            incidents = status_res.get("incidents", {}) if isinstance(status_res, dict) else {}
            if incidents:
                self.current_incident_id = list(incidents.keys())[-1]
            else:
                self.print_alexa("There is no recent fix to undo.")
                return

        rb_res = self.call_mcp_tool("rollback_fix", {"incident_id": self.current_incident_id})
        self.print_alexa(
            rb_res.get("spoken", "Restored previous state."),
            f"rollback_fix(incident_id='{self.current_incident_id}')",
        )

    def handle_inject(self, flaky: bool = False) -> None:
        """Inject test outage (Simulation test fixture helper)."""
        mode_desc = "flaky extender (fails verification demo)" if flaky else "standard extender outage"
        self.print_system(f"Simulating outage: {mode_desc}...")
        self._post(
            "/api/inject_failure",
            {"device_id": "wifi_extender", "mode": "offline", "fail_verification": flaky},
        )
        self.print_system("Failure injected! Check dashboard at http://127.0.0.1:8000/")

    def handle_clear(self) -> None:
        """Clear all simulated outages (Simulation test fixture helper)."""
        self.print_system("Clearing all outages and resetting devices...")
        self._post("/api/clear_failures", {})
        self.current_incident_id = None
        self.print_system("All devices restored to online!")

    def dispatch(self, user_input: str) -> bool:
        """Dispatch conversational user voice prompt to appropriate handler."""
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
        print("  Connected to MCP Endpoint: " + self.mcp_url)
        print("  Type natural voice commands or 'help' for phrases. 'exit' to quit.")
        print("=" * 65 + "\n")

        # Test MCP connectivity
        status_res = self.call_mcp_tool("home_status", {})
        if "error" in status_res:
            print(f"\033[91m⚠️ Warning: HomeGuard MCP endpoint not responding at {self.mcp_url}\033[0m")
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
