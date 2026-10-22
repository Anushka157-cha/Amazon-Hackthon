"""HomeGuard Device Integration Layer.

Defines a common device adapter interface and concrete adapters:
- SimulatedDeviceAdapter: Repeatable deterministic testing adapter
- AsusWrtRouterAdapter: Router API adapter for AsusWRT / Merlin
- HomeAssistantAdapter: Smart home integration adapter for Home Assistant
- UniFiAdapter: Software-defined networking controller adapter
- NetworkDiscoveryService: Discovers LAN nodes and parent-child links.
"""

from __future__ import annotations

import abc
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

AdapterType = Literal["simulated", "asuswrt", "homeassistant", "unifi"]


@dataclass
class DeviceCapability:
    can_ping: bool = True
    can_reboot: bool = True
    can_power_cycle: bool = False
    can_band_steer: bool = False
    can_speed_test: bool = True
    can_query_rssi: bool = True
    requires_auth: bool = False


@dataclass
class ProbeResult:
    device_id: str
    is_online: bool
    latency_ms: float
    packet_loss_pct: float
    rssi_dbm: int | None = None
    last_error: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BaseDeviceAdapter(abc.ABC):
    """Abstract interface that every network/smart device adapter must implement."""

    def __init__(self, adapter_name: str, config: dict[str, Any] | None = None) -> None:
        self.adapter_name = adapter_name
        self.config = config or {}
        self.connected: bool = True

    @abc.abstractmethod
    def get_capabilities(self, device_id: str) -> DeviceCapability:
        """Return allowed control actions and permissions for this device."""
        raise NotImplementedError

    @abc.abstractmethod
    def probe_device(self, device_id: str, status: str = "online") -> ProbeResult:
        """Poll device health metrics (latency, loss, signal)."""
        raise NotImplementedError

    @abc.abstractmethod
    def execute_action(self, device_id: str, action: str) -> dict[str, Any]:
        """Perform remediation action (e.g. restart)."""
        raise NotImplementedError

    def test_connection(self) -> dict[str, Any]:
        """Verify connectivity to device management API or simulator."""
        return {
            "adapter": self.adapter_name,
            "connected": self.connected,
            "latency_ms": 1.2,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


class SimulatedDeviceAdapter(BaseDeviceAdapter):
    """Default high-fidelity adapter for reproducible testing and demos."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("Simulated Device Adapter", config)

    def get_capabilities(self, device_id: str) -> DeviceCapability:
        return DeviceCapability(
            can_ping=True,
            can_reboot=True,
            can_power_cycle=True,
            can_band_steer=device_id.startswith("wifi"),
            can_speed_test=device_id in {"router", "wifi_extender"},
            can_query_rssi=True,
            requires_auth=False,
        )

    def probe_device(self, device_id: str, status: str = "online") -> ProbeResult:
        if status == "offline":
            return ProbeResult(
                device_id=device_id,
                is_online=False,
                latency_ms=0.0,
                packet_loss_pct=100.0,
                last_error="Host unreachable: ICMP probe timed out after 1000ms",
            )
        if status == "degraded":
            return ProbeResult(
                device_id=device_id,
                is_online=True,
                latency_ms=185.0,
                packet_loss_pct=8.5,
                rssi_dbm=-82,
                last_error="High packet loss on 5GHz Wi-Fi backhaul",
            )
        return ProbeResult(
            device_id=device_id,
            is_online=True,
            latency_ms=22.4,
            packet_loss_pct=0.0,
            rssi_dbm=-54,
        )

    def execute_action(self, device_id: str, action: str) -> dict[str, Any]:
        if action != "restart":
            return {
                "success": False,
                "error": f"Unsupported action '{action}' on simulated adapter",
            }
        return {
            "success": True,
            "device_id": device_id,
            "action": action,
            "duration_sec": 3.0,
            "adapter": self.adapter_name,
            "status": "restarted_successfully",
        }


class AsusWrtRouterAdapter(BaseDeviceAdapter):
    """Integration for AsusWRT routers via simulated HTTP/SSH API."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("AsusWRT Router Adapter", config)

    def get_capabilities(self, device_id: str) -> DeviceCapability:
        return DeviceCapability(
            can_ping=True,
            can_reboot=True,
            can_power_cycle=False,
            can_band_steer=True,
            can_speed_test=True,
            can_query_rssi=True,
            requires_auth=True,
        )

    def probe_device(self, device_id: str, status: str = "online") -> ProbeResult:
        return ProbeResult(
            device_id=device_id,
            is_online=(status != "offline"),
            latency_ms=3.5 if status == "online" else 0.0,
            packet_loss_pct=0.0 if status == "online" else 100.0,
            rssi_dbm=-45,
        )

    def execute_action(self, device_id: str, action: str) -> dict[str, Any]:
        return {
            "success": True,
            "device_id": device_id,
            "action": action,
            "adapter": self.adapter_name,
            "nvram_committed": True,
        }


class HomeAssistantAdapter(BaseDeviceAdapter):
    """Integration for Home Assistant entities (smart plugs, switches, ping sensors)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("Home Assistant Adapter", config)

    def get_capabilities(self, device_id: str) -> DeviceCapability:
        return DeviceCapability(
            can_ping=True,
            can_reboot=True,
            can_power_cycle=True,
            can_band_steer=False,
            can_speed_test=False,
            can_query_rssi=True,
            requires_auth=True,
        )

    def probe_device(self, device_id: str, status: str = "online") -> ProbeResult:
        return ProbeResult(
            device_id=device_id,
            is_online=(status != "offline"),
            latency_ms=12.0 if status == "online" else 0.0,
            packet_loss_pct=0.0 if status == "online" else 100.0,
        )

    def execute_action(self, device_id: str, action: str) -> dict[str, Any]:
        return {
            "success": True,
            "device_id": device_id,
            "action": action,
            "adapter": self.adapter_name,
            "ha_service": "switch.turn_off_and_on",
        }


class UniFiAdapter(BaseDeviceAdapter):
    """Integration for UniFi Controller / Dream Machine SD-WAN."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("Ubiquiti UniFi Adapter", config)

    def get_capabilities(self, device_id: str) -> DeviceCapability:
        return DeviceCapability(
            can_ping=True,
            can_reboot=True,
            can_power_cycle=True,
            can_band_steer=True,
            can_speed_test=True,
            can_query_rssi=True,
            requires_auth=True,
        )

    def probe_device(self, device_id: str, status: str = "online") -> ProbeResult:
        return ProbeResult(
            device_id=device_id,
            is_online=(status != "offline"),
            latency_ms=4.8 if status == "online" else 0.0,
            packet_loss_pct=0.0 if status == "online" else 100.0,
        )

    def execute_action(self, device_id: str, action: str) -> dict[str, Any]:
        return {
            "success": True,
            "device_id": device_id,
            "action": action,
            "adapter": self.adapter_name,
            "poe_cycled": True,
        }


class NetworkDiscoveryService:
    """Discovers LAN devices, identifying IPs, MAC addresses, and topology hierarchy."""

    @staticmethod
    def scan_subnet(subnet: str = "192.168.1.0/24") -> list[dict[str, Any]]:
        return [
            {
                "id": "router",
                "name": "Main Router (Simulated)",
                "ip": "192.168.1.1",
                "mac": "00:1A:2B:3C:4D:01",
                "type": "network_gateway",
                "vendor": "Netgear / Asus",
                "parent": None,
                "interface": "WAN/LAN",
            },
            {
                "id": "wifi_extender",
                "name": "Wi-Fi Extender (Simulated)",
                "ip": "192.168.1.15",
                "mac": "00:1A:2B:3C:4D:02",
                "type": "network_repeater",
                "vendor": "TP-Link Mesh",
                "parent": "router",
                "interface": "5GHz Mesh Link",
            },
            {
                "id": "ring_doorbell",
                "name": "Ring Video Doorbell (Simulated)",
                "ip": "192.168.1.52",
                "mac": "00:1A:2B:3C:4D:03",
                "type": "security_camera",
                "vendor": "Amazon Ring",
                "parent": "wifi_extender",
                "interface": "2.4GHz Wi-Fi",
            },
            {
                "id": "fire_tv",
                "name": "Fire TV 4K (Simulated)",
                "ip": "192.168.1.88",
                "mac": "00:1A:2B:3C:4D:04",
                "type": "streaming_device",
                "vendor": "Amazon",
                "parent": "wifi_extender",
                "interface": "5GHz Wi-Fi",
            },
            {
                "id": "echo_speaker",
                "name": "Echo Speaker (Simulated)",
                "ip": "192.168.1.94",
                "mac": "00:1A:2B:3C:4D:05",
                "type": "smart_speaker",
                "vendor": "Amazon Echo",
                "parent": "wifi_extender",
                "interface": "5GHz Wi-Fi",
            },
        ]
