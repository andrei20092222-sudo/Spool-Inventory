"""Diagnostics for Spool Inventory: the data and settings, for bug reports."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SpoolInventoryConfigEntry
from .const import STORAGE_VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SpoolInventoryConfigEntry
) -> dict[str, Any]:
    """Return everything the integration stores (no credentials are kept)."""
    manager = entry.runtime_data
    return {
        "storage_version": STORAGE_VERSION,
        "summary": manager.summary(),
        "settings": manager.settings,
        "export": manager.export_data(),
        "recently_deleted": manager.trash_summary(),
    }
