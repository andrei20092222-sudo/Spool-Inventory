"""Websocket API used by the Filament panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_INVENTORY_CHANGED
from .manager import SpoolManager
from .services import (
    _WEIGHT,
    _WEIGHT_POSITIVE,
    ADD_SPOOL_SCHEMA,
    CONSUME_SCHEMA,
    UPDATE_SPOOL_SCHEMA,
    WEIGH_SPOOL_SCHEMA,
    _color,
)

_SPOOL_ID = {vol.Required("spool_id"): str}

_CATALOG_KEY = {
    vol.Required("vendor"): vol.All(cv.string, vol.Length(min=1, max=60)),
    vol.Required("material"): vol.All(cv.string, vol.Length(min=1, max=30)),
    vol.Optional("line", default=""): vol.All(cv.string, vol.Length(max=60)),
    vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=80)),
}


def _manager(hass: HomeAssistant) -> SpoolManager:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return entries[0].runtime_data


def _payload(manager: SpoolManager) -> dict[str, Any]:
    return {
        "spools": [s.as_dict() for s in manager.spools],
        "summary": manager.summary(),
        "trash": manager.trash_summary(),
        "equipment": manager.equipment.payload(),
        "settings": manager.settings,
        "user_catalog": manager.user_catalog,
    }


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the panel's commands."""
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_add)
    websocket_api.async_register_command(hass, ws_update)
    websocket_api.async_register_command(hass, ws_weigh)
    websocket_api.async_register_command(hass, ws_consume)
    websocket_api.async_register_command(hass, ws_delete)
    websocket_api.async_register_command(hass, ws_history)
    for command in _EQUIPMENT_COMMANDS:
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_archive)
    websocket_api.async_register_command(hass, ws_restore)
    websocket_api.async_register_command(hass, ws_rebuy)
    websocket_api.async_register_command(hass, ws_export)
    websocket_api.async_register_command(hass, ws_import)
    websocket_api.async_register_command(hass, ws_settings)
    websocket_api.async_register_command(hass, ws_catalog_add)
    websocket_api.async_register_command(hass, ws_catalog_remove)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@websocket_api.async_response
async def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the inventory now and again after every change."""
    _manager(hass)  # fail early when the integration is not loaded

    @callback
    def _send() -> None:
        # look the manager up each time so a reloaded entry is picked up
        connection.send_message(websocket_api.event_message(msg["id"], _payload(_manager(hass))))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_INVENTORY_CHANGED, _send
    )
    connection.send_result(msg["id"])
    _send()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/add", **ADD_SPOOL_SCHEMA.schema}
)
@websocket_api.async_response
async def ws_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create a spool."""
    data = {k: v for k, v in msg.items() if k not in ("id", "type")}
    spool = _manager(hass).async_add(data)
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/update", **_SPOOL_ID, **UPDATE_SPOOL_SCHEMA}
)
@websocket_api.async_response
async def ws_update(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change fields of a spool."""
    changes = {k: v for k, v in msg.items() if k not in ("id", "type", "spool_id")}
    spool = _manager(hass).async_update(msg["spool_id"], changes)
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/weigh", **_SPOOL_ID, **WEIGH_SPOOL_SCHEMA}
)
@websocket_api.async_response
async def ws_weigh(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Set remaining filament from a scale reading."""
    spool = _manager(hass).async_weigh(
        msg["spool_id"], msg["gross_weight"], msg.get("spool_weight")
    )
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/consume", **_SPOOL_ID, **CONSUME_SCHEMA}
)
@websocket_api.async_response
async def ws_consume(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Subtract used filament."""
    spool = _manager(hass).async_consume(msg["spool_id"], msg["grams"])
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/delete", **_SPOOL_ID}
)
@websocket_api.async_response
async def ws_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove a spool."""
    _manager(hass).async_delete(msg["spool_id"])
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings",
        vol.Optional("low_threshold"): vol.All(vol.Coerce(float), vol.Range(min=0, max=5000)),
        vol.Optional("notify"): cv.boolean,
        vol.Optional("currency"): vol.All(cv.string, vol.Length(max=8)),
        vol.Optional("locations"): vol.All([vol.All(cv.string, vol.Length(max=60))], vol.Length(max=60)),
    }
)
@websocket_api.async_response
async def ws_settings(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change the alert threshold, notifications and the location list."""
    changes = {k: v for k, v in msg.items() if k not in ("id", "type")}
    connection.send_result(msg["id"], _manager(hass).async_update_settings(changes))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/catalog_add",
        **_CATALOG_KEY,
        vol.Optional("hex"): _color,
        vol.Optional("weights"): vol.All([_WEIGHT_POSITIVE], vol.Length(min=1, max=6)),
        vol.Optional("tare"): _WEIGHT,
    }
)
@websocket_api.async_response
async def ws_catalog_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save a custom entry into the user's own catalog."""
    entry = {k: v for k, v in msg.items() if k not in ("id", "type")}
    connection.send_result(msg["id"], _manager(hass).async_catalog_add(entry))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/catalog_remove", **_CATALOG_KEY}
)
@websocket_api.async_response
async def ws_catalog_remove(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove an entry from the user's own catalog."""
    entry = {k: v for k, v in msg.items() if k not in ("id", "type")}
    _manager(hass).async_catalog_remove(entry)
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/archive", **_SPOOL_ID, vol.Optional("archived", default=True): cv.boolean}
)
@websocket_api.async_response
async def ws_archive(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Archive a finished spool, or bring an archived one back."""
    spool = _manager(hass).async_archive(msg["spool_id"], msg["archived"])
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/restore", **_SPOOL_ID})
@websocket_api.async_response
async def ws_restore(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Undo a delete."""
    spool = _manager(hass).async_restore_deleted(msg["spool_id"])
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/rebuy", **_SPOOL_ID})
@websocket_api.async_response
async def ws_rebuy(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add a new full spool like this one."""
    spool = _manager(hass).async_rebuy(msg["spool_id"])
    connection.send_result(msg["id"], spool.as_dict())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/export"})
@websocket_api.async_response
async def ws_export(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a backup of the whole inventory."""
    connection.send_result(msg["id"], _manager(hass).export_data())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/import", vol.Required("data"): dict, vol.Required("replace"): cv.boolean}
)
@websocket_api.async_response
async def ws_import(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Load a backup file (add what is missing, or replace everything)."""
    result = await _manager(hass).async_import(msg["data"], msg["replace"])
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Optional("spool_id"): cv.string,
        vol.Optional("limit", default=200): vol.All(vol.Coerce(int), vol.Range(min=1, max=2000)),
    }
)
@websocket_api.async_response
async def ws_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """What happened to one spool (or to all), newest first."""
    connection.send_result(msg["id"], _manager(hass).history(msg.get("spool_id"), msg["limit"]))


# ---- printers, maintenance tasks, parts and consumables (v0.6.0) ------------

_ITEM_FIELDS = {
    vol.Optional("printer_id"): cv.string,
    vol.Optional("category"): vol.All(cv.string, vol.Length(max=40)),
    vol.Optional("name"): vol.All(cv.string, vol.Length(min=1, max=80)),
    vol.Optional("quantity"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
    vol.Optional("unit"): vol.All(cv.string, vol.Length(max=12)),
    vol.Optional("low_at"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
    vol.Optional("notes"): vol.All(cv.string, vol.Length(max=300)),
    vol.Optional("reorder"): cv.boolean,
}
_INTERVAL = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))


def _equipment_command(name: str, schema: dict, handler):
    """Build an admin-only command that answers with the changed record (or nothing)."""

    @websocket_api.require_admin
    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/{name}", **schema})
    @websocket_api.async_response
    async def command(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
        result = handler(_manager(hass).equipment, msg)
        connection.send_result(msg["id"], result)

    command.__name__ = f"ws_{name}"
    return command


_EQUIPMENT_COMMANDS = [
    _equipment_command("printer_add", {vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=60)), vol.Optional("model", default=""): vol.All(cv.string, vol.Length(max=60)), vol.Optional("starter", default=False): cv.boolean},
                       lambda e, m: e.printer_add(m["name"], m["model"], m["starter"])),
    _equipment_command("printer_update", {vol.Required("printer_id"): cv.string, vol.Optional("name"): cv.string, vol.Optional("model"): cv.string, vol.Optional("notes"): cv.string},
                       lambda e, m: e.printer_update(m["printer_id"], m)),
    _equipment_command("printer_delete", {vol.Required("printer_id"): cv.string}, lambda e, m: e.printer_delete(m["printer_id"])),
    _equipment_command("task_add", {vol.Required("printer_id"): cv.string, vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=80)), vol.Required("interval_days"): _INTERVAL, vol.Optional("last_done"): cv.string, vol.Optional("notes", default=""): cv.string},
                       lambda e, m: e.task_add(m["printer_id"], m["name"], m["interval_days"], m.get("last_done"), m["notes"])),
    _equipment_command("task_update", {vol.Required("task_id"): cv.string, vol.Optional("name"): cv.string, vol.Optional("interval_days"): _INTERVAL, vol.Optional("last_done"): cv.string, vol.Optional("notes"): cv.string},
                       lambda e, m: e.task_update(m["task_id"], m)),
    _equipment_command("task_done", {vol.Required("task_id"): cv.string, vol.Optional("date"): cv.string, vol.Optional("note", default=""): vol.All(cv.string, vol.Length(max=200))},
                       lambda e, m: e.task_done(m["task_id"], m.get("date"), m["note"])),
    _equipment_command("task_delete", {vol.Required("task_id"): cv.string}, lambda e, m: e.task_delete(m["task_id"])),
    _equipment_command("item_add", {vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=80)), **{k: v for k, v in _ITEM_FIELDS.items() if k.schema != "name"}},
                       lambda e, m: e.item_add(m)),
    _equipment_command("item_update", {vol.Required("item_id"): cv.string, **_ITEM_FIELDS}, lambda e, m: e.item_update(m["item_id"], m)),
    _equipment_command("item_adjust", {vol.Required("item_id"): cv.string, vol.Required("delta"): vol.Coerce(float)}, lambda e, m: e.item_adjust(m["item_id"], m["delta"])),
    _equipment_command("item_delete", {vol.Required("item_id"): cv.string}, lambda e, m: e.item_delete(m["item_id"])),
]
