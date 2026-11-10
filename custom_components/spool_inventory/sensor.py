"""Sensors: one per spool, plus inventory summary sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    device_registry as dr,
    entity_platform,
    entity_registry as er,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpoolInventoryConfigEntry
from .const import (
    DOMAIN,
    SIGNAL_INVENTORY_CHANGED,
    SIGNAL_SPOOL_ADDED,
    SIGNAL_SPOOL_REMOVED,
    signal_spool_updated,
)
from .manager import Spool, SpoolManager
from .services import CONSUME_SCHEMA, UPDATE_SPOOL_SCHEMA, WEIGH_SPOOL_SCHEMA

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpoolInventoryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create summary sensors and one sensor per stored spool."""
    manager = entry.runtime_data

    # Parent device that every spool device hangs off.
    parent = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Spool Inventory",
        entry_type=DeviceEntryType.SERVICE,
    )
    manager.parent_device_id = parent.id

    async_add_entities(
        [TotalFilamentSensor(entry, manager), SpoolCountSensor(entry, manager), MaintenanceSensor(entry, manager), LowItemsSensor(entry, manager)]
    )
    async_add_entities(SpoolSensor(entry, manager, s.id) for s in manager.active_spools)

    @callback
    def _spool_added(spool_id: str) -> None:
        async_add_entities([SpoolSensor(entry, manager, spool_id)])

    @callback
    def _spool_removed(spool_id: str) -> None:
        """Drop the spool's device (and with it the sensor) from the registries."""
        ent_reg = er.async_get(hass)
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, spool_id)
        if entity_id and (reg_entry := ent_reg.async_get(entity_id)):
            if reg_entry.device_id:
                dr.async_get(hass).async_remove_device(reg_entry.device_id)
            else:
                ent_reg.async_remove(entity_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SPOOL_ADDED, _spool_added)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SPOOL_REMOVED, _spool_removed)
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "weigh_spool", WEIGH_SPOOL_SCHEMA, "async_weigh_spool"
    )
    platform.async_register_entity_service(
        "consume_filament", CONSUME_SCHEMA, "async_consume_filament"
    )
    platform.async_register_entity_service(
        "update_spool", UPDATE_SPOOL_SCHEMA, "async_update_spool"
    )
    platform.async_register_entity_service(
        "delete_spool", None, "async_delete_spool"
    )


def _not_a_spool() -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key="not_a_spool"
    )


class _InventoryEntity(SensorEntity):
    """Common base. Spool actions fail cleanly on non-spool entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        self._entry = entry
        self.manager = manager

    async def async_weigh_spool(
        self, gross_weight: float, spool_weight: float | None = None
    ) -> None:
        raise _not_a_spool()

    async def async_consume_filament(self, grams: float) -> None:
        raise _not_a_spool()

    async def async_update_spool(self, **changes: Any) -> None:
        raise _not_a_spool()

    async def async_delete_spool(self) -> None:
        raise _not_a_spool()


class SpoolSensor(_InventoryEntity):
    """Remaining filament (grams) of one spool; everything else is attributes."""

    _attr_name = None  # the spool's device name is the entity name
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:printer-3d-nozzle"

    def __init__(
        self, entry: SpoolInventoryConfigEntry, manager: SpoolManager, spool_id: str
    ) -> None:
        super().__init__(entry, manager)
        self._spool_id = spool_id
        self._attr_unique_id = spool_id
        spool = manager.get(spool_id)
        assert spool is not None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spool_id)},
            name=spool.display_name,
            manufacturer=spool.vendor,
            model=self._model(spool),
            via_device_id=manager.parent_device_id,
        )

    @staticmethod
    def _model(spool: Spool) -> str:
        return f"{spool.material} {spool.diameter:g} mm"

    @property
    def _spool(self) -> Spool | None:
        return self.manager.get(self._spool_id)

    @property
    def available(self) -> bool:
        return self._spool is not None

    @property
    def native_value(self) -> float | None:
        spool = self._spool
        return None if spool is None else round(spool.remaining_weight, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        spool = self._spool
        if spool is None:
            return None
        data = spool.as_dict()
        data["spool_id"] = data.pop("id")
        return data

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_spool_updated(self._spool_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        if (spool := self._spool) is not None:
            self._sync_device(spool)
        self.async_write_ha_state()

    @callback
    def _sync_device(self, spool: Spool) -> None:
        """Keep the device registry in step with edited spools."""
        if self.registry_entry is None or self.registry_entry.device_id is None:
            return
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get(self.registry_entry.device_id)
        wanted = (spool.display_name, spool.vendor, self._model(spool))
        if device is None or (device.name, device.manufacturer, device.model) == wanted:
            return
        dev_reg.async_update_device(
            device.id, name=wanted[0], manufacturer=wanted[1], model=wanted[2]
        )

    # ---- entity services ---------------------------------------------

    async def async_weigh_spool(
        self, gross_weight: float, spool_weight: float | None = None
    ) -> None:
        self.manager.async_weigh(self._spool_id, gross_weight, spool_weight)

    async def async_consume_filament(self, grams: float) -> None:
        self.manager.async_consume(self._spool_id, grams)

    async def async_update_spool(self, **changes: Any) -> None:
        self.manager.async_update(self._spool_id, changes)

    async def async_delete_spool(self) -> None:
        # The platform's removal listener drops the device and this entity.
        self.manager.async_delete(self._spool_id)


class _SummarySensor(_InventoryEntity):
    """Base for inventory-wide sensors."""

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        super().__init__(entry, manager)
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_INVENTORY_CHANGED, self._handle_change
            )
        )

    @callback
    def _handle_change(self) -> None:
        self.async_write_ha_state()


class TotalFilamentSensor(_SummarySensor):
    """Total filament left across all spools."""

    _attr_translation_key = "total_filament"
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:scale"

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        super().__init__(entry, manager)
        self._attr_unique_id = f"{entry.entry_id}_total_filament"

    @property
    def native_value(self) -> float:
        return self.manager.summary()["total_remaining"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self.manager.summary()
        return {
            "breakdown": summary["breakdown"],
            "by_material": summary["by_material"],
            "by_color": summary["by_color"],
            "by_vendor": summary["by_vendor"],
            "by_location": summary["by_location"],
        }


class SpoolCountSensor(_SummarySensor):
    """Number of spools in the inventory."""

    _attr_translation_key = "spool_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        super().__init__(entry, manager)
        self._attr_unique_id = f"{entry.entry_id}_spool_count"

    @property
    def native_value(self) -> int:
        return self.manager.summary()["count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self.manager.summary()
        spools = self.manager.spools
        return {
            "empty_spools": summary["empty"],
            "low_spools": summary["low"],
            "low_threshold": summary["threshold"],
            "archived_spools": summary["archived"],
            "loaded": [s.display_name for s in spools if s.loaded],
            "to_reorder": [s.display_name for s in spools if s.reorder],
        }


class MaintenanceSensor(_SummarySensor):
    """How many maintenance tasks are overdue."""

    _attr_translation_key = "maintenance_overdue"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wrench-clock"

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        super().__init__(entry, manager)
        self._attr_unique_id = f"{entry.entry_id}_maintenance_overdue"

    @property
    def native_value(self) -> int:
        return len(self.manager.equipment.overdue())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        eq = self.manager.equipment
        names = {p["id"]: p["name"] for p in eq.printers}
        tasks = eq.payload()["tasks"]
        return {
            "overdue": [f"{names.get(t['printer_id'], '')}: {t['name']}".strip(": ") for t in tasks if t["state"] == "overdue"],
            "due_soon": [f"{names.get(t['printer_id'], '')}: {t['name']}".strip(": ") for t in tasks if t["state"] == "soon"],
            "next_due": min((t["due_date"] for t in tasks), default=None),
        }


class LowItemsSensor(_SummarySensor):
    """How many parts / consumables are low or marked for reorder."""

    _attr_translation_key = "items_low"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:package-variant-closed-remove"

    def __init__(self, entry: SpoolInventoryConfigEntry, manager: SpoolManager) -> None:
        super().__init__(entry, manager)
        self._attr_unique_id = f"{entry.entry_id}_items_low"

    @property
    def native_value(self) -> int:
        return len(self.manager.equipment.low_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"items": [f"{i['name']} ({i['quantity']:g} {i['unit']})".replace(" )", ")") for i in self.manager.equipment.low_items()]}
