"""History log and diagnostics (v0.5.0)."""

from homeassistant.core import HomeAssistant

from custom_components.spool_inventory.const import DOMAIN, HISTORY_MAX

from .test_features import _add
from .test_spool_inventory import _setup


async def test_history_records_changes(hass: HomeAssistant, hass_storage) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", remaining_weight=800)
    m.async_consume(a, 100)
    m.async_weigh(a, 900, 200)
    m.async_update(a, {"remaining_weight": 650, "location": "Drier"})
    m.async_update(a, {"loaded": True, "reorder": True})  # flags are not logged
    m.async_update(a, {"notes": "same"})
    m.async_archive(a)
    m.async_archive(a, False)
    rows = m.history(a)
    assert [r["action"] for r in rows] == ["unarchived", "archived", "edited", "edited", "weighed", "used", "added"]
    used = rows[5]
    assert (used["before"], used["after"], used["note"]) == (800, 700, "100 g")
    weighed = rows[4]
    assert (weighed["before"], weighed["after"]) == (700, 700.0) and "900" in weighed["note"]
    edited = rows[3]
    assert (edited["before"], edited["after"], edited["note"]) == (700, 650, "location")
    assert rows[2]["before"] is None and rows[2]["note"] == "notes"
    # the "same value" update logged nothing extra
    assert len(rows) == 7
    # persisted
    await m.async_flush()
    assert len(hass_storage["spool_inventory.spools"]["data"]["history"]) == 7


async def test_history_survives_delete_restore_rebuy(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", reorder=True)
    new = m.async_rebuy(a)
    m.async_delete(new.id)
    m.async_restore_deleted(new.id)
    actions = [r["action"] for r in m.history(new.id)]
    assert actions == ["restored", "deleted", "added"]
    assert m.history(a)[0]["action"] == "bought another"
    assert len(m.history()) == 5  # all spools, newest first
    assert m.history(limit=2)[0]["action"] == "restored"


async def test_history_is_capped_and_in_backup(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black")
    for _ in range(HISTORY_MAX + 20):
        m.async_consume(a, 0.1)
    assert len(m.history(limit=2000)) == HISTORY_MAX
    backup = m.export_data()
    assert len(backup["history"]) == HISTORY_MAX
    m.async_delete(a)
    await m.async_import(backup, replace=True)
    assert len(m.history(limit=2000)) == HISTORY_MAX
    # merging the same backup again adds nothing
    await m.async_import(backup, replace=False)
    assert len(m.history(limit=2000)) == HISTORY_MAX


async def test_history_command_and_diagnostics(hass: HomeAssistant, hass_ws_client) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    a = await _add(hass, "Galaxy Black")
    m.async_consume(a, 50)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/history", "spool_id": a, "limit": 1})
    res = await client.receive_json()
    assert res["success"] and [r["action"] for r in res["result"]] == ["used"]

    from custom_components.spool_inventory.diagnostics import async_get_config_entry_diagnostics

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["storage_version"] == 2 and diag["export"]["format"] == "spool_inventory_backup"
    assert len(diag["export"]["spools"]) == 1 and len(diag["export"]["history"]) == 2
