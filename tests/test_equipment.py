"""Printers, maintenance tasks, parts and consumables (v0.6.0)."""

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.spool_inventory.const import DOMAIN, EVENT_ITEM_LOW, EVENT_TASK_DUE

from .test_spool_inventory import _setup


def _notes(hass):
    return persistent_notification._async_get_or_create_notifications(hass)


def _ago(days: int) -> str:
    return (dt_util.now().date() - timedelta(days=days)).isoformat()


async def test_printer_with_starter_tasks(hass: HomeAssistant) -> None:
    eq = (await _setup(hass)).runtime_data.equipment
    p = eq.printer_add("Core One+", "Prusa", starter=True)
    assert len(eq.tasks) == 6 and all(t["printer_id"] == p["id"] for t in eq.tasks)
    payload = eq.payload()
    assert all(t["state"] in ("ok", "soon") for t in payload["tasks"])
    assert [t["days_left"] for t in payload["tasks"]][:2] == [7, 30]
    assert payload["tasks"][0]["state"] == "soon"  # weekly task is due within 7 days
    with pytest.raises(ServiceValidationError):
        eq.printer_add("  ")
    # deleting a printer removes its tasks and detaches its items
    item = eq.item_add({"name": "Nozzle 0.4", "printer_id": p["id"], "quantity": 2})
    eq.printer_delete(p["id"])
    assert eq.printers == [] and eq.tasks == [] and eq.items[0]["printer_id"] == ""
    assert item["id"] == eq.items[0]["id"]


async def test_task_overdue_alert_done_and_recheck(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    eq = m.equipment
    events = async_capture_events(hass, EVENT_TASK_DUE)
    p = eq.printer_add("Core One+")
    t = eq.task_add(p["id"], "Lubricate rods", 30, last_done=_ago(20))
    assert eq.overdue() == [] and not events
    # time passes: the hourly check notices the task is overdue
    eq.tasks[0]["last_done"] = _ago(45)  # the calendar moved on, nobody edited the task
    assert eq.payload()["tasks"][0]["state"] == "overdue"
    eq.check_tasks()
    await hass.async_block_till_done()
    assert len(events) == 1 and events[0].data["days_overdue"] == 15 and events[0].data["printer"] == "Core One+"
    assert _notes(hass)[f"{DOMAIN}_task_{t['id']}"]["title"] == "Maintenance due"
    eq.check_tasks()  # again: no second event
    await hass.async_block_till_done()
    assert len(events) == 1
    assert hass.states.get("sensor.spool_inventory_maintenance_overdue").state == "1"
    assert "Core One+: Lubricate rods" in hass.states.get("sensor.spool_inventory_maintenance_overdue").attributes["overdue"]
    eq.task_done(t["id"], note="used PTFE grease")
    await hass.async_block_till_done()
    assert eq.overdue() == [] and f"{DOMAIN}_task_{t['id']}" not in _notes(hass)
    assert m.history(t["id"])[0]["action"] == "maintenance done" and m.history(t["id"])[0]["note"] == "used PTFE grease"
    with pytest.raises(ServiceValidationError):
        eq.task_done(t["id"], (dt_util.now().date() + timedelta(days=2)).isoformat())
    with pytest.raises(ServiceValidationError):
        eq.task_update(t["id"], {"interval_days": 0})
    # notifications can be switched off
    m.async_update_settings({"notify": False})
    eq.task_update(t["id"], {"last_done": _ago(90)})
    eq.check_tasks()
    assert f"{DOMAIN}_task_{t['id']}" not in _notes(hass)


async def test_items_low_alert_adjust_and_sensor(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    eq = m.equipment
    low = async_capture_events(hass, EVENT_ITEM_LOW)
    ipa = eq.item_add({"name": "IPA 99%", "category": "Consumable", "quantity": 500, "unit": "ml", "low_at": 100})
    quiet = eq.item_add({"name": "Wipes", "quantity": 5, "low_at": 10})  # added already low: no alert
    await hass.async_block_till_done()
    assert not low
    eq.item_adjust(ipa["id"], -450)
    await hass.async_block_till_done()
    assert len(low) == 1 and low[0].data["name"] == "IPA 99%"
    assert _notes(hass)[f"{DOMAIN}_item_{ipa['id']}"]["title"] == "Running low"
    eq.item_adjust(ipa["id"], -10)  # still low: no second event
    assert len(low) == 1
    eq.item_adjust(ipa["id"], -1000)  # never below zero
    assert eq._item(ipa["id"])["quantity"] == 0
    state = hass.states.get("sensor.spool_inventory_parts_and_consumables_low")
    assert state.state == "2"
    eq.item_adjust(ipa["id"], 500)  # refilled: alert cleared
    assert f"{DOMAIN}_item_{ipa['id']}" not in _notes(hass)
    assert [i["to_reorder"] for i in eq.payload()["items"]] == [False, True]
    eq.item_update(quiet["id"], {"reorder": True, "low_at": 0})
    assert eq.payload()["items"][1]["to_reorder"] is True and eq.payload()["items"][1]["low"] is False
    with pytest.raises(ServiceValidationError):
        eq.item_add({"name": " "})
    with pytest.raises(ServiceValidationError):
        eq.item_add({"name": "x", "printer_id": "nope"})


async def test_equipment_persists_and_is_in_backup(hass: HomeAssistant, hass_storage) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    p = m.equipment.printer_add("Core One+", starter=True)
    m.equipment.item_add({"name": "Nozzle 0.4 hardened", "category": "Nozzle", "quantity": 3, "printer_id": p["id"]})
    await m.async_flush()
    saved = hass_storage["spool_inventory.spools"]["data"]["equipment"]
    assert len(saved["printers"]) == 1 and len(saved["tasks"]) == 6 and len(saved["items"]) == 1
    assert hass.config_entries.async_reload(entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    eq = entry.runtime_data.equipment
    assert len(eq.printers) == 1 and len(eq.tasks) == 6 and eq.items[0]["name"] == "Nozzle 0.4 hardened"

    backup = eq._m.export_data()
    assert len(backup["equipment"]["tasks"]) == 6
    eq.printer_delete(eq.printers[0]["id"])
    await eq._m.async_import(backup, replace=False)  # merge brings it back
    assert len(eq.printers) == 1 and len(eq.tasks) == 6
    await eq._m.async_import(backup, replace=False)  # and does not duplicate
    assert len(eq.printers) == 1 and len(eq.tasks) == 6 and len(eq.items) == 1
    eq.printer_add("Second")
    await eq._m.async_import(backup, replace=True)
    assert [p["name"] for p in eq.printers] == ["Core One+"]


async def test_equipment_websocket_commands_and_admin(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    m = (await _setup(hass)).runtime_data
    client = await hass_ws_client(hass)

    async def cmd(payload):
        await client.send_json_auto_id(payload)
        while (res := await client.receive_json())["type"] != "result":
            pass
        return res

    res = await cmd({"type": f"{DOMAIN}/printer_add", "name": "Core One+", "starter": True})
    assert res["success"]
    pid = res["result"]["id"]
    res = await cmd({"type": f"{DOMAIN}/item_add", "name": "Nozzle", "quantity": 2, "category": "Nozzle", "printer_id": pid})
    assert res["success"]
    iid = res["result"]["id"]
    assert (await cmd({"type": f"{DOMAIN}/item_adjust", "item_id": iid, "delta": -1}))["success"]
    assert m.equipment._item(iid)["quantity"] == 1
    tid = m.equipment.tasks[0]["id"]
    assert (await cmd({"type": f"{DOMAIN}/task_done", "task_id": tid}))["success"]
    assert not (await cmd({"type": f"{DOMAIN}/task_add", "printer_id": pid, "name": "x", "interval_days": 0}))["success"]
    assert not (await cmd({"type": f"{DOMAIN}/task_done", "task_id": "nope"}))["success"]
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    msgs = [await client.receive_json() for _ in range(2)]
    event = next(x for x in msgs if x["type"] == "event")["event"]
    assert event["equipment"]["printers"][0]["name"] == "Core One+" and len(event["equipment"]["tasks"]) == 6

    ro = await hass_ws_client(hass, hass_read_only_access_token)
    for p in ({"type": f"{DOMAIN}/printer_add", "name": "x"}, {"type": f"{DOMAIN}/task_done", "task_id": tid},
              {"type": f"{DOMAIN}/item_adjust", "item_id": iid, "delta": 1}, {"type": f"{DOMAIN}/item_delete", "item_id": iid}):
        await ro.send_json_auto_id(p)
        r = await ro.receive_json()
        assert not r["success"] and r["error"]["code"] == "unauthorized"
