"""Bluetooth discovery helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant


async def async_scan_devices(hass: HomeAssistant, connectable: bool = True) -> list[Any]:
    """Return BLE devices from Home Assistant discovery."""
    try:
        from homeassistant.components.bluetooth import async_discovered_service_info

        return [
            info.device
            for info in async_discovered_service_info(hass, connectable)
        ]
    except Exception:
        from bleak import BleakScanner

        return await BleakScanner.discover(timeout=5.0)
