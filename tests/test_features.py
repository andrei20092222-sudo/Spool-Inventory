"""Loaded flag, reorder flag, low/empty alerts, settings and the user's own catalog."""

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.spool_inventory.const import DOMAIN, EVENT_EMPTY, EVENT_LOW

from .test_panel_api import _next_event, _subscribe
from .test_spool_inventory import _setup


async def _add(hass: HomeAssistant, color: str, **extra) -> str:
    data = {"vendor": "Prusament", "material": "PETG", "color_name": color, **extra}
    result = await hass.services.async_call(
        DOMAIN, "add_spool", data, blocking=True, return_response=True
    )
    return result["spool_id"]


def _notes(hass: HomeAssistant) -> dict:
    return persistent_notification._async_get_or_create_notifications(hass)


async def test_loaded_and_reorder_flags(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    a = await _add(hass, "Galaxy Black", location="Drier", loaded=True)
    b = await _add(hass, "Pistachio Green", location="Bedroom storage")
    assert manager.get(a).loaded is True and manager.get(b).loaded is False

    sensor_b = "sensor.prusament_petg_pistachio_green"
    await hass.services.async_call(
        DOMAIN, "update_spool", {"entity_id": sensor_b, "reorder": True, "loaded": True},
        blocking=True,
    )
    assert hass.states.get(sensor_b).attributes["reorder"] is True
    assert hass.states.get(sensor_b).attributes["loaded"] is True

    summary = manager.summary()
    assert (summary["loaded"], summary["reorder"]) == (2, 1)
    assert summary["by_location"] == {"Bedroom storage": 1000.0, "Drier": 1000.0}

    counts = hass.states.get("sensor.spool_inventory_spool_count").attributes
    assert counts["loaded"] == ["Prusament PETG Galaxy Black", "Prusament PETG Pistachio Green"]
    assert counts["to_reorder"] == ["Prusament PETG Pistachio Green"]

    async def listed(**filters):
        res = await hass.services.async_call(
            DOMAIN, "list_spools", filters, blocking=True, return_response=True
        )
        return [s["color_name"] for s in res["spools"]]

    assert await listed(reorder=True) == ["Pistachio Green"]
    assert await listed(loaded=False) == []
    assert await listed(location="drier") == ["Galaxy Black"]


async def test_low_and_empty_alerts(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    low, empty = async_capture_events(hass, EVENT_LOW), async_capture_events(hass, EVENT_EMPTY)
    # a spool added already low raises nothing
    quiet = await _add(hass, "Quiet", remaining_weight=80)
    await hass.async_block_till_done()
    assert not low and not empty and not _notes(hass)

    sid = await _add(hass, "Galaxy Black", location="Drier")
    sensor = "sensor.prusament_petg_galaxy_black"

    async def use(grams):
        await hass.services.async_call(
            DOMAIN, "consume_filament", {"entity_id": sensor, "grams": grams}, blocking=True
        )
        await hass.async_block_till_done()

    await use(500)  # 500 g left: fine
    assert not low and not empty
    await use(400)  # 100 g left: low (threshold 150)
    assert len(low) == 1 and not empty
    assert low[0].data["name"] == "Prusament PETG Galaxy Black"
    assert low[0].data["remaining_weight"] == 100 and low[0].data["threshold"] == 150
    assert _notes(hass)[f"{DOMAIN}_{sid}"]["title"] == "Filament low"
    await use(10)  # still low: no second event
    assert len(low) == 1
    await use(1000)  # empty
    assert len(empty) == 1 and len(low) == 1
    assert _notes(hass)[f"{DOMAIN}_{sid}"]["title"] == "Filament empty"

    # refilled / re-weighed above the threshold clears the notification
    await hass.services.async_call(
        DOMAIN, "weigh_spool", {"entity_id": sensor, "gross_weight": 1200, "spool_weight": 200},
        blocking=True,
    )
    assert f"{DOMAIN}_{sid}" not in _notes(hass)
    # dropping again alerts again
    await use(900)
    assert len(low) == 2

    manager.async_delete(sid)
    assert f"{DOMAIN}_{sid}" not in _notes(hass)
    assert manager.get(quiet) is not None


async def test_settings_threshold_notify_and_locations(hass: HomeAssistant, hass_ws_client) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    client = await hass_ws_client(hass)
    first = await _subscribe(client)
    assert first["settings"]["low_threshold"] == 150
    assert first["settings"]["locations"] == ["Bedroom storage", "Drier", "Small bedroom storage"]
    assert first["user_catalog"] == []

    sid = await _add(hass, "Sky Blue", remaining_weight=200)
    await _next_event(client)
    low = async_capture_events(hass, EVENT_LOW)

    # raising the threshold re-evaluates silently (no event, no notification)...
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "low_threshold": 250, "locations": [" Drier", "drier", "Shelf"]})
    msgs = [await client.receive_json() for _ in range(2)]
    result = next(m for m in msgs if m["type"] == "result")
    assert result["success"] and result["result"]["locations"] == ["Drier", "Shelf"]
    pushed = next(m for m in msgs if m["type"] == "event")["event"]
    assert pushed["summary"]["low"] == 1 and pushed["summary"]["threshold"] == 250
    await hass.async_block_till_done()
    assert not low and not _notes(hass)
    # ...and later changes use it
    manager.async_update(sid, {"remaining_weight": 100})
    assert len(low) == 0  # it was already low under the new threshold: no repeat

    # notifications can be switched off
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "notify": False})
    while (done := await client.receive_json())["type"] != "result":
        pass
    assert done["success"] and done["result"]["notify"] is False
    other = await _add(hass, "Other", remaining_weight=900)
    manager.async_update(other, {"remaining_weight": 10})
    await hass.async_block_till_done()
    assert len(low) == 1 and f"{DOMAIN}_{other}" not in _notes(hass)

    # bad values are refused
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "low_threshold": -5})
    while (bad := await client.receive_json())["type"] != "result":
        pass
    assert not bad["success"], bad


async def test_user_catalog_roundtrip_and_persistence(hass: HomeAssistant, hass_ws_client, hass_storage) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await _subscribe(client)

    async def cmd(payload):
        await client.send_json_auto_id(payload)
        msgs = []
        while True:
            m = await client.receive_json()
            msgs.append(m)
            if m["type"] == "result":
                events = [x for x in msgs if x["type"] == "event"]
                if not events:  # the push can arrive right after the result
                    events = [await client.receive_json()]
                return m, events[0]["event"]

    entry_msg = {
        "type": f"{DOMAIN}/catalog_add", "vendor": "Fiberlogy", "material": "PETG",
        "line": "Easy", "name": "Pistachio Green", "hex": "#A8D08D", "weights": [850], "tare": 190,
    }
    result, pushed = await cmd(entry_msg)
    assert result["success"], result
    assert pushed["user_catalog"] == [
        {"vendor": "Fiberlogy", "material": "PETG", "line": "Easy", "name": "Pistachio Green",
         "hex": "#a8d08d", "weights": [850.0], "tare": 190.0}
    ]
    # the same entry again replaces it instead of duplicating
    result, pushed = await cmd({**entry_msg, "hex": "#b0d090"})
    assert len(pushed["user_catalog"]) == 1 and pushed["user_catalog"][0]["hex"] == "#b0d090"

    await entry.runtime_data.async_flush()
    saved = hass_storage["spool_inventory.spools"]["data"]
    assert saved["catalog"][0]["name"] == "Pistachio Green"
    assert saved["settings"]["low_threshold"] == 150

    # survives a reload
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.user_catalog[0]["vendor"] == "Fiberlogy"

    # removal, and removing something that is not there is harmless
    result, pushed = await cmd({"type": f"{DOMAIN}/catalog_remove", "vendor": "fiberlogy", "material": "petg", "line": "Easy", "name": "pistachio green"})
    assert result["success"] and pushed["user_catalog"] == []
    result, _ = await cmd({"type": f"{DOMAIN}/catalog_remove", "vendor": "x", "material": "y", "name": "z"})
    assert result["success"]


async def test_new_commands_need_admin(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for payload in (
        {"type": f"{DOMAIN}/settings", "notify": False},
        {"type": f"{DOMAIN}/catalog_add", "vendor": "a", "material": "b", "name": "c"},
        {"type": f"{DOMAIN}/catalog_remove", "vendor": "a", "material": "b", "name": "c"},
    ):
        await client.send_json_auto_id(payload)
        res = await client.receive_json()
        assert not res["success"] and res["error"]["code"] == "unauthorized"


async def test_old_stored_data_still_loads(hass: HomeAssistant, hass_storage) -> None:
    """Data written by v0.2.x (no flags, no settings, no catalog) loads with defaults."""
    hass_storage["spool_inventory.spools"] = {
        "version": 1,
        "minor_version": 1,
        "key": "spool_inventory.spools",
        "data": {"spools": [{
            "id": "abc", "vendor": "Prusament", "material": "PETG", "color_name": "Jet Black",
            "remaining_weight": 120.0, "created": "x", "updated": "x"}]},
    }
    entry = await _setup(hass)
    spool = entry.runtime_data.get("abc")
    assert spool.loaded is False and spool.reorder is False
    assert entry.runtime_data.settings["low_threshold"] == 150
    assert entry.runtime_data.summary()["low"] == 1
    with pytest.raises(ServiceValidationError):
        entry.runtime_data.async_update("nope", {})
