"""Tests for the Spool Inventory integration."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.spool_inventory.const import DOMAIN

SPOOL = "sensor.prusament_petg_galaxy_black"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Spool Inventory", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _add(hass: HomeAssistant, **extra) -> dict:
    data = {
        "vendor": "Prusament",
        "material": "PETG",
        "color_name": "Galaxy Black",
        "color": [10, 20, 30],
        "initial_weight": 1000,
        "spool_weight": 210,
        "gross_weight": 1130,
        **extra,
    }
    resp = await hass.services.async_call(
        DOMAIN, "add_spool", data, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    return resp


async def test_add_from_gross_weight(hass: HomeAssistant) -> None:
    await _setup(hass)
    resp = await _add(hass)
    assert resp["name"] == "Prusament PETG Galaxy Black"

    state = hass.states.get(SPOOL)
    assert state is not None
    assert float(state.state) == 920.0
    assert state.attributes["unit_of_measurement"] == "g"
    assert state.attributes["remaining_percent"] == 92.0
    assert state.attributes["gross_weight"] == 1130.0
    assert state.attributes["color_hex"] == "#0a141e"
    assert state.attributes["spool_id"] == resp["spool_id"]

    assert float(hass.states.get("sensor.spool_inventory_total_filament").state) == 920.0
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "1"


async def test_defaults_to_full_spool(hass: HomeAssistant) -> None:
    await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        "add_spool",
        {"vendor": "Fiberlogy", "material": "PLA"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.fiberlogy_pla")
    assert float(state.state) == 1000.0


async def test_weigh_consume_update(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _add(hass)

    await hass.services.async_call(
        DOMAIN, "weigh_spool", {"entity_id": SPOOL, "gross_weight": 900}, blocking=True
    )
    assert float(hass.states.get(SPOOL).state) == 690.0

    await hass.services.async_call(
        DOMAIN, "consume_filament", {"entity_id": SPOOL, "grams": 40.5}, blocking=True
    )
    assert float(hass.states.get(SPOOL).state) == 649.5

    await hass.services.async_call(
        DOMAIN, "consume_filament", {"entity_id": SPOOL, "grams": 5000}, blocking=True
    )
    assert float(hass.states.get(SPOOL).state) == 0.0
    assert hass.states.get("sensor.spool_inventory_spool_count").attributes["empty_spools"] == 1

    await hass.services.async_call(
        DOMAIN,
        "update_spool",
        {"entity_id": SPOOL, "location": "Shelf A", "remaining_weight": 500},
        blocking=True,
    )
    state = hass.states.get(SPOOL)
    assert float(state.state) == 500.0
    assert state.attributes["location"] == "Shelf A"

    await hass.services.async_call(
        DOMAIN, "update_spool", {"entity_id": SPOOL, "color_name": "Jet Black"}, blocking=True
    )
    await hass.async_block_till_done()
    device_id = er.async_get(hass).async_get(SPOOL).device_id
    device = dr.async_get(hass).async_get(device_id)
    assert device.name == "Prusament PETG Jet Black"
    assert device.via_device_id is not None  # child of the "Spool Inventory" device


async def test_delete_removes_entity_and_device(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _add(hass)
    device_id = er.async_get(hass).async_get(SPOOL).device_id
    assert dr.async_get(hass).async_get(device_id) is not None
    await hass.services.async_call(
        DOMAIN, "delete_spool", {"entity_id": SPOOL}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(SPOOL) is None
    assert er.async_get(hass).async_get(SPOOL) is None
    assert dr.async_get(hass).async_get(device_id) is None
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "0"
    assert float(hass.states.get("sensor.spool_inventory_total_filament").state) == 0.0


async def test_list_spools_filter(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _add(hass)
    await _add(hass, vendor="Fiberlogy", material="PLA", color_name="White")

    everything = await hass.services.async_call(
        DOMAIN, "list_spools", {}, blocking=True, return_response=True
    )
    assert len(everything["spools"]) == 2

    petg = await hass.services.async_call(
        DOMAIN, "list_spools", {"material": "petg"}, blocking=True, return_response=True
    )
    assert [s["vendor"] for s in petg["spools"]] == ["Prusament"]

    total = hass.states.get("sensor.spool_inventory_total_filament")
    assert total.attributes["by_material"] == {"PETG": 920.0, "PLA": 920.0}


async def test_validation_errors(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError):  # gross below the empty spool
        await _add(hass, gross_weight=100)
    with pytest.raises(ServiceValidationError):  # both inputs
        await _add(hass, remaining_weight=500)
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "0"

    await _add(hass)
    with pytest.raises(ServiceValidationError):  # action on a summary sensor
        await hass.services.async_call(
            DOMAIN,
            "consume_filament",
            {"entity_id": "sensor.spool_inventory_total_filament", "grams": 1},
            blocking=True,
        )


async def test_persistence_across_reload(hass: HomeAssistant, hass_storage) -> None:
    entry = await _setup(hass)
    resp = await _add(hass)
    await hass.services.async_call(
        DOMAIN, "consume_filament", {"entity_id": SPOOL, "grams": 20}, blocking=True
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "spool_inventory.spools" in hass_storage

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(SPOOL)
    assert float(state.state) == 900.0
    assert state.attributes["spool_id"] == resp["spool_id"]
    # no duplicate entities after reload
    assert len(hass.states.async_entity_ids("sensor")) == 5  # 4 summary sensors + 1 spool
