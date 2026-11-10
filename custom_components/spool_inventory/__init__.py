"""Spool Inventory: a local filament spool inventory for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_URL_PATH, PANEL_WEBCOMPONENT, STATIC_URL
from .manager import SpoolManager
from .services import async_register_services
from .websocket_api import async_register_websocket_api

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type SpoolInventoryConfigEntry = ConfigEntry[SpoolManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions, the websocket API and the static files once."""
    async_register_services(hass)
    async_register_websocket_api(hass)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL, str(Path(__file__).parent / "www"), cache_headers=False
            )
        ]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SpoolInventoryConfigEntry) -> bool:
    """Load stored spools, create the sensors and add the sidebar panel."""
    manager = SpoolManager(hass)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # maintenance tasks become overdue with the calendar, so look at them every hour
    entry.async_on_unload(
        async_track_time_interval(hass, lambda _now: manager.equipment.check_tasks(), timedelta(hours=1))
    )

    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_WEBCOMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_URL}/panel.js?v={version}",
        sidebar_title="Filament",
        sidebar_icon="mdi:printer-3d-nozzle",
        require_admin=False,
        config={"static_url": STATIC_URL, "version": str(version)},
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpoolInventoryConfigEntry) -> bool:
    """Unload sensors, remove the panel and flush data to disk."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        await entry.runtime_data.async_flush()
    return unloaded
