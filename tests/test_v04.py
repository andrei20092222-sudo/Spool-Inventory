"""Archive, undo delete, rebuy, backup/restore and storage upgrade (v0.4.0)."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.spool_inventory.const import DOMAIN

from .test_features import _add
from .test_spool_inventory import _setup


async def test_archive_hides_from_totals_sensor_and_alerts(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", remaining_weight=10, loaded=True)
    await _add(hass, "Sky Blue")
    assert hass.states.get("sensor.prusament_petg_galaxy_black")
    m.async_archive(a)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.prusament_petg_galaxy_black") is None
    s = m.summary()
    assert (s["count"], s["low"], s["loaded"], s["archived"]) == (1, 0, 0, 1)
    assert s["total_remaining"] == 1000
    assert m.get(a).archived and m.get(a).archived_at
    m.async_archive(a, False)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.prusament_petg_galaxy_black")
    assert m.summary()["count"] == 2


async def test_delete_can_be_undone(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", remaining_weight=321)
    m.async_delete(a)
    await hass.async_block_till_done()
    assert m.get(a) is None and m.trash_summary()[0]["remaining_weight"] == 321
    m.async_restore_deleted(a)
    await hass.async_block_till_done()
    assert m.get(a).remaining_weight == 321 and not m.trash_summary()
    assert hass.states.get("sensor.prusament_petg_galaxy_black")
    with pytest.raises(ServiceValidationError):
        m.async_restore_deleted(a)


async def test_trash_is_capped_and_persisted(hass: HomeAssistant, hass_storage) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    for i in range(30):
        m.async_delete(await _add(hass, f"C{i}"))
    assert len(m.trash_summary()) == 25
    await m.async_flush()
    assert len(hass_storage["spool_inventory.spools"]["data"]["trash"]) == 25


async def test_rebuy(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", remaining_weight=30, location="Drier", reorder=True, price=25)
    new = m.async_rebuy(a)
    await hass.async_block_till_done()
    assert new.id != a and new.remaining_weight == new.initial_weight == 1000
    assert (new.location, new.price, new.reorder, new.loaded) == ("Drier", 25, False, False)
    assert m.get(a).reorder is False and m.get(a).remaining_weight == 30
    assert m.summary()["reorder"] == 0 and m.summary()["count"] == 2


async def test_weigh_sets_date(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black")
    assert m.get(a).weighed == ""
    m.async_weigh(a, 700, 200)
    assert m.get(a).weighed


async def test_export_import_merge_and_replace(hass: HomeAssistant, hass_storage) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", remaining_weight=500)
    m.async_catalog_add({"vendor": "Fib", "material": "PETG", "name": "X", "weights": [850]})
    backup = m.export_data()
    assert backup["format"] == "spool_inventory_backup" and len(backup["spools"]) == 1

    # merge: nothing duplicated, missing things come back
    m.async_delete(a)
    res = await m.async_import(backup, replace=False)
    assert res["added"] == 1 and m.get(a).remaining_weight == 500
    res = await m.async_import(backup, replace=False)
    assert res["added"] == 0 and len(m.spools) == 1 and len(m.user_catalog) == 1

    # replace: current data swapped, a safety copy of the old state is kept
    await _add(hass, "Extra")
    res = await m.async_import(backup, replace=True)
    await hass.async_block_till_done()
    assert res["replaced"] and [s.id for s in m.spools] == [a]
    saved = hass_storage["spool_inventory.backup_before_restore"]["data"]
    assert len(saved["spools"]) == 2
    assert hass.states.get("sensor.prusament_petg_extra") is None
    assert hass.states.get("sensor.prusament_petg_galaxy_black")


async def test_import_rejects_garbage_and_skips_bad_rows(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    for bad in ({}, {"format": "nope", "spools": []}, {"format": "spool_inventory_backup"}):
        with pytest.raises(ServiceValidationError):
            await m.async_import(bad, replace=True)
    assert m.spools == []
    good = {"id": "g", "vendor": "Prusament", "material": "PLA", "remaining_weight": "250"}
    res = await m.async_import(
        {"format": "spool_inventory_backup", "spools": [good, {"id": "x"}, "junk", {**good, "id": "h", "remaining_weight": "abc"}]},
        replace=False,
    )
    assert res == {"added": 1, "skipped": 3, "replaced": False}
    assert m.get("g").remaining_weight == 250.0


async def test_migration_from_v1_keeps_a_copy(hass: HomeAssistant, hass_storage) -> None:
    old = {"spools": [{"id": "abc", "vendor": "Prusament", "material": "PETG", "color_name": "Jet Black", "remaining_weight": 120.0}]}
    hass_storage["spool_inventory.spools"] = {"version": 1, "minor_version": 1, "key": "spool_inventory.spools", "data": old}
    entry = await _setup(hass)
    assert entry.runtime_data.get("abc").remaining_weight == 120.0
    assert hass_storage["spool_inventory.backup_before_upgrade"]["data"] == old
    await entry.runtime_data.async_flush()
    assert hass_storage["spool_inventory.spools"]["version"] == 2
    assert hass_storage["spool_inventory.backup_daily"]["data"]["data"]["spools"]


async def test_new_commands_need_admin(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for p in ({"type": f"{DOMAIN}/archive", "spool_id": "a"}, {"type": f"{DOMAIN}/restore", "spool_id": "a"},
              {"type": f"{DOMAIN}/rebuy", "spool_id": "a"}, {"type": f"{DOMAIN}/export"},
              {"type": f"{DOMAIN}/import", "data": {}, "replace": True}):
        await client.send_json_auto_id(p)
        res = await client.receive_json()
        assert not res["success"] and res["error"]["code"] == "unauthorized"


async def test_currency_setting(hass: HomeAssistant, hass_ws_client) -> None:
    m = (await _setup(hass)).runtime_data
    assert m.settings["currency"] == "RON"
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "currency": " EUR "})
    while (res := await client.receive_json())["type"] != "result":
        pass
    assert res["success"] and m.settings["currency"] == "EUR"
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "currency": "  "})
    while (res := await client.receive_json())["type"] != "result":
        pass
    assert m.settings["currency"] == "RON"  # blank falls back to the default
    await client.send_json_auto_id({"type": f"{DOMAIN}/settings", "currency": "x" * 20})
    while (res := await client.receive_json())["type"] != "result":
        pass
    assert not res["success"]
    # it is part of the backup and restore
    m.async_update_settings({"currency": "USD"})
    backup = m.export_data()
    m.async_update_settings({"currency": "EUR"})
    await m.async_import(backup, replace=True)
    assert m.settings["currency"] == "USD"


async def test_refill_flag_roundtrip_and_rebuy(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    a = await _add(hass, "Galaxy Black", refill=True, initial_weight=900, spool_weight=190, reorder=True)
    s = m.get(a)
    assert s.refill and s.initial_weight == 900 and s.remaining_weight == 900
    assert hass.states.get("sensor.prusament_petg_galaxy_black").attributes.get("refill") is True
    new = m.async_rebuy(a)
    assert new.refill and new.remaining_weight == 900 and new.spool_weight == 190
    backup = m.export_data()
    await m.async_import(backup, replace=True)
    assert all(x.refill for x in m.spools)
