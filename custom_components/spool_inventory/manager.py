"""Persistent spool storage and business logic."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from datetime import timedelta
import logging
from typing import Any
import uuid

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_COLOR_HEX,
    DEFAULT_DIAMETER,
    DEFAULT_INITIAL_WEIGHT,
    BACKUP_KEY,
    DEFAULT_SETTINGS,
    DOMAIN,
    EVENT_EMPTY,
    EVENT_LOW,
    EXPORT_FORMAT,
    HISTORY_MAX,
    MAX_USER_CATALOG,
    PRE_IMPORT_KEY,
    PRE_MIGRATION_KEY,
    SAVE_DELAY,
    SIGNAL_INVENTORY_CHANGED,
    SIGNAL_SPOOL_ADDED,
    SIGNAL_SPOOL_REMOVED,
    STORAGE_KEY,
    STORAGE_VERSION,
    TRASH_MAX,
    signal_spool_updated,
)
from .equipment import Equipment  # noqa: E402

_LOGGER = logging.getLogger(__name__)

# Fields a user may change through update_spool (service key -> Spool field).
UPDATABLE_FIELDS: dict[str, str] = {
    "vendor": "vendor",
    "material": "material",
    "product": "product",
    "color_name": "color_name",
    "color": "color_hex",
    "diameter": "diameter",
    "initial_weight": "initial_weight",
    "spool_weight": "spool_weight",
    "remaining_weight": "remaining_weight",
    "price": "price",
    "location": "location",
    "notes": "notes",
    "tag_id": "tag_id",
    "loaded": "loaded",
    "reorder": "reorder",
    "refill": "refill",
}

_RANK = {"ok": 0, "low": 1, "empty": 2}

_TEXT_FIELDS = {
    "vendor",
    "material",
    "product",
    "color_name",
    "location",
    "notes",
    "tag_id",
}


@dataclass
class Spool:
    """One physical spool of filament."""

    id: str
    vendor: str
    material: str  # base type, e.g. PETG
    product: str = ""  # product line, e.g. "Matte PETG"; empty when same as material
    color_name: str = ""
    color_hex: str = DEFAULT_COLOR_HEX
    diameter: float = DEFAULT_DIAMETER
    initial_weight: float = DEFAULT_INITIAL_WEIGHT  # net filament, new spool (g)
    spool_weight: float = 0.0  # empty spool / tare (g)
    remaining_weight: float = DEFAULT_INITIAL_WEIGHT  # net filament left (g)
    price: float | None = None
    location: str = ""
    notes: str = ""
    tag_id: str = ""  # reserved for the future NFC integration
    loaded: bool = False  # currently loaded in the printer
    reorder: bool = False  # on the "need to reorder" list
    refill: bool = False  # a spool-less refill on a reusable spool (e.g. Prusament 900 g)
    archived: bool = False  # finished: kept as a record, no sensor, not counted
    archived_at: str = ""
    weighed: str = ""  # when it was last set from a scale reading
    created: str = ""
    updated: str = ""

    @property
    def display_name(self) -> str:
        """Human readable name, e.g. 'Prusament PETG Prusa Galaxy Black'."""
        return " ".join(
            p for p in (self.vendor, self.product or self.material, self.color_name) if p
        )

    @property
    def gross_weight(self) -> float:
        """Expected weight on a scale: filament plus empty spool."""
        return self.remaining_weight + self.spool_weight

    @property
    def remaining_percent(self) -> float:
        """Remaining filament as a percentage of a new spool (0-100)."""
        if self.initial_weight <= 0:
            return 0.0
        return round(min(100.0, self.remaining_weight / self.initial_weight * 100), 1)

    def as_dict(self) -> dict[str, Any]:
        """Return stored fields plus computed ones (for services/attributes)."""
        data = asdict(self)
        data["name"] = self.display_name
        data["gross_weight"] = round(self.gross_weight, 1)
        data["remaining_percent"] = self.remaining_percent
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Spool:
        """Build a spool from stored data, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class _SpoolStore(Store[dict[str, Any]]):
    """Store with a format upgrade that keeps a copy of the old file first."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        if old_major_version < 2:
            await Store(self.hass, 1, PRE_MIGRATION_KEY).async_save(old_data)
            data = dict(old_data)
            data.setdefault("settings", {})
            data.setdefault("catalog", [])
            data.setdefault("trash", [])
            return data
        return old_data


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


class SpoolManager:
    """Owns the spool collection and persists it."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self._store = _SpoolStore(hass, STORAGE_VERSION, STORAGE_KEY)
        self._backup_store: Store[dict[str, Any]] = Store(hass, 1, BACKUP_KEY)
        self._trash: list[dict[str, Any]] = []  # deleted spools that can be restored
        self._history: list[dict[str, Any]] = []  # what happened to the spools, oldest first
        self.equipment = Equipment(self)  # printers, maintenance tasks, parts and consumables
        self._spools: dict[str, Spool] = {}
        self._settings: dict[str, Any] = {
            **DEFAULT_SETTINGS,
            "locations": list(DEFAULT_SETTINGS["locations"]),
        }
        # The user's own catalog entries ("save my custom entry to the catalog").
        self._user_catalog: list[dict[str, Any]] = []
        # Last known stock status per spool: ok / low / empty (for the alerts).
        self._alerts: dict[str, str] = {}
        # Set by the sensor platform; spool devices are children of this device.
        self.parent_device_id: str | None = None

    # ---- persistence -------------------------------------------------

    async def async_load(self) -> None:
        """Load spools, settings and the user's catalog from disk."""
        data = await self._store.async_load() or {}
        for item in data.get("spools", []):
            try:
                spool = Spool.from_dict(item)
            except (TypeError, ValueError):
                _LOGGER.warning("Skipping unreadable spool record: %s", item)
                continue
            self._spools[spool.id] = spool
        stored = data.get("settings")
        if isinstance(stored, dict):
            for key in self._settings:
                if key in stored:
                    self._settings[key] = stored[key]
        catalog = data.get("catalog")
        if isinstance(catalog, list):
            self._user_catalog = [e for e in catalog if isinstance(e, dict)]
        self.equipment.load(data.get("equipment") if isinstance(data.get("equipment"), dict) else {})
        history = data.get("history")
        if isinstance(history, list):
            self._history = [e for e in history if isinstance(e, dict) and e.get("id")][-HISTORY_MAX:]
        trash = data.get("trash")
        if isinstance(trash, list):
            self._trash = [e for e in trash if isinstance(e, dict) and e.get("id")][:TRASH_MAX]
        self._alerts = {s.id: self._status(s) for s in self._spools.values()}
        await self._async_daily_backup(data)

    async def _async_daily_backup(self, data: dict[str, Any]) -> None:
        """Keep one extra copy of the data, refreshed at most once a day."""
        if not (data.get("spools") or data.get("catalog")):
            return
        previous = await self._backup_store.async_load() or {}
        saved = dt_util.parse_datetime(str(previous.get("saved", "")))
        if saved is None or dt_util.utcnow() - saved > timedelta(hours=24):
            await self._backup_store.async_save(
                {"saved": dt_util.utcnow().isoformat(), "data": data}
            )

    async def async_flush(self) -> None:
        """Write pending data immediately."""
        await self._store.async_save(self._data_to_save())

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "spools": [asdict(s) for s in self._spools.values()],
            "settings": self._settings,
            "catalog": self._user_catalog,
            "trash": self._trash,
            "history": self._history,
            "equipment": self.equipment.as_data(),
        }

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)

    # ---- queries -----------------------------------------------------

    @property
    def spools(self) -> list[Spool]:
        """All spools, sorted by name."""
        return sorted(self._spools.values(), key=lambda s: s.display_name.lower())

    def get(self, spool_id: str) -> Spool | None:
        """Return one spool or None."""
        return self._spools.get(spool_id)

    def _require(self, spool_id: str) -> Spool:
        if (spool := self._spools.get(spool_id)) is None:
            raise _error("spool_not_found", spool_id=spool_id)
        return spool

    def _log(
        self,
        spool: Spool,
        action: str,
        before: float | None = None,
        after: float | None = None,
        note: str = "",
    ) -> None:
        """Remember what happened to a spool (shown in its history)."""
        self._history.append(
            {
                "t": dt_util.utcnow().isoformat(),
                "id": spool.id,
                "name": spool.display_name,
                "action": action,
                "before": None if before is None else round(float(before), 1),
                "after": None if after is None else round(float(after), 1),
                "note": note,
            }
        )
        del self._history[:-HISTORY_MAX]

    def log_raw(self, ident: str, name: str, action: str, note: str = "") -> None:
        """History entry for something that is not a spool (a printer, a task, an item)."""
        self._history.append({"t": dt_util.utcnow().isoformat(), "id": ident, "name": name, "action": action, "before": None, "after": None, "note": note})
        del self._history[:-HISTORY_MAX]

    def history(self, spool_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """Newest first, for one spool or for all of them."""
        rows = [e for e in reversed(self._history) if spool_id is None or e["id"] == spool_id]
        return rows[:limit]

    @property
    def active_spools(self) -> list[Spool]:
        """Spools that are not archived, sorted by name."""
        return [s for s in self.spools if not s.archived]

    def trash_summary(self) -> list[dict[str, Any]]:
        """Recently deleted spools (newest first) that can be restored."""
        out = []
        for entry in self._trash:
            try:
                spool = Spool.from_dict(entry)
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "id": spool.id,
                    "name": spool.display_name,
                    "remaining_weight": round(float(spool.remaining_weight), 1),
                    "deleted_at": entry.get("deleted_at", ""),
                }
            )
        return out

    @property
    def settings(self) -> dict[str, Any]:
        """Alert threshold, notification switch and the usual locations."""
        return self._settings

    @property
    def user_catalog(self) -> list[dict[str, Any]]:
        """Catalog entries the user saved from custom spools."""
        return self._user_catalog

    @property
    def low_threshold(self) -> float:
        """Grams below which a spool counts as low."""
        return float(self._settings["low_threshold"])

    def _status(self, spool: Spool) -> str:
        if spool.archived:
            return "ok"
        if spool.remaining_weight <= 0:
            return "empty"
        if spool.remaining_weight < self.low_threshold:
            return "low"
        return "ok"

    def summary(self) -> dict[str, Any]:
        """Aggregate numbers for the summary sensors."""
        by_material: dict[str, float] = {}
        by_vendor: dict[str, float] = {}
        by_color: dict[str, float] = {}
        by_location: dict[str, float] = {}
        total = 0.0
        empty = low = loaded = 0
        reorder = sum(1 for s in self._spools.values() if s.reorder)  # archived ones may be reordered too
        for spool in self.active_spools:
            total += spool.remaining_weight
            loc = spool.location or "No location"
            by_location[loc] = by_location.get(loc, 0.0) + spool.remaining_weight
            status = self._status(spool)
            low += status == "low"
            loaded += bool(spool.loaded)
            by_material[spool.material] = (
                by_material.get(spool.material, 0.0) + spool.remaining_weight
            )
            color_key = " ".join(p for p in (spool.material, spool.color_name) if p)
            by_color[color_key] = by_color.get(color_key, 0.0) + spool.remaining_weight
            by_vendor[spool.vendor] = (
                by_vendor.get(spool.vendor, 0.0) + spool.remaining_weight
            )
            if spool.remaining_weight <= 0:
                empty += 1
        return {
            "count": len(self.active_spools),
            "empty": empty,
            "low": low,
            "loaded": loaded,
            "reorder": reorder,
            "archived": sum(1 for s in self._spools.values() if s.archived),
            "tasks_overdue": len(self.equipment.overdue()),
            "items_low": len(self.equipment.low_items()),
            "threshold": self.low_threshold,
            "by_location": {k: round(v, 1) for k, v in sorted(by_location.items())},
            "total_remaining": round(total, 1),
            "by_material": {k: round(v, 1) for k, v in sorted(by_material.items())},
            "by_vendor": {k: round(v, 1) for k, v in sorted(by_vendor.items())},
            "by_color": {k: round(v, 1) for k, v in sorted(by_color.items())},
            # grams left on each individual spool, by display name
            "breakdown": {
                s.display_name: round(s.remaining_weight, 1) for s in self.active_spools
            },
        }

    # ---- mutations ---------------------------------------------------

    @staticmethod
    def _net_from_gross(gross: float, tare: float) -> float:
        if gross < tare:
            raise _error(
                "gross_below_tare", gross=f"{gross:g}", tare=f"{tare:g}"
            )
        return gross - tare

    @callback
    def _notify(self, spool_id: str) -> None:
        async_dispatcher_send(self.hass, signal_spool_updated(spool_id))
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)

    @callback
    def async_add(self, data: dict[str, Any]) -> Spool:
        """Create a spool. Remaining weight may come from gross or net input."""
        data = dict(data)
        gross = data.pop("gross_weight", None)
        remaining = data.pop("remaining_weight", None)
        if gross is not None and remaining is not None:
            raise _error("weight_conflict")

        tare = float(data.get("spool_weight", 0.0))
        initial = float(data.get("initial_weight", DEFAULT_INITIAL_WEIGHT))
        if gross is not None:
            remaining = self._net_from_gross(float(gross), tare)
        elif remaining is None:
            remaining = initial

        now = dt_util.utcnow().isoformat()
        spool = Spool(
            id=uuid.uuid4().hex,
            vendor=data["vendor"].strip(),
            material=data["material"].strip(),
            product=data.get("product", "").strip(),
            color_name=data.get("color_name", "").strip(),
            color_hex=data.get("color", DEFAULT_COLOR_HEX),
            diameter=float(data.get("diameter", DEFAULT_DIAMETER)),
            initial_weight=initial,
            spool_weight=tare,
            remaining_weight=float(remaining),
            price=data.get("price"),
            location=data.get("location", "").strip(),
            notes=data.get("notes", "").strip(),
            tag_id=data.get("tag_id", "").strip(),
            loaded=bool(data.get("loaded", False)),
            reorder=bool(data.get("reorder", False)),
            refill=bool(data.get("refill", False)),
            created=now,
            updated=now,
        )
        self._spools[spool.id] = spool
        self._alerts[spool.id] = self._status(spool)  # a new entry never raises an alert
        self._log(spool, "added", None, spool.remaining_weight)
        self._schedule_save()
        async_dispatcher_send(self.hass, SIGNAL_SPOOL_ADDED, spool.id)
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return spool

    @callback
    def async_update(self, spool_id: str, changes: dict[str, Any]) -> Spool:
        """Change descriptive fields and/or weights of a spool."""
        spool = self._require(spool_id)
        before = spool.remaining_weight
        changed: list[str] = []
        for key, value in changes.items():
            field_name = UPDATABLE_FIELDS.get(key)
            if field_name is None:
                continue
            if field_name in _TEXT_FIELDS and isinstance(value, str):
                value = value.strip()
            if getattr(spool, field_name) != value and field_name not in ("loaded", "reorder"):
                changed.append(field_name)
            setattr(spool, field_name, value)
        spool.remaining_weight = max(0.0, float(spool.remaining_weight))
        if changed:
            weight = abs(spool.remaining_weight - before) > 0.04
            self._log(
                spool,
                "edited",
                before if weight else None,
                spool.remaining_weight if weight else None,
                ", ".join(f.replace("_", " ") for f in changed if f != "remaining_weight"),
            )
        self._touch(spool)
        return spool

    @callback
    def async_weigh(
        self, spool_id: str, gross_weight: float, spool_weight: float | None = None
    ) -> Spool:
        """Set remaining filament from a scale reading (spool + filament)."""
        spool = self._require(spool_id)
        before = spool.remaining_weight
        if spool_weight is not None:
            spool.spool_weight = float(spool_weight)
        spool.remaining_weight = self._net_from_gross(
            float(gross_weight), spool.spool_weight
        )
        spool.weighed = dt_util.utcnow().isoformat()
        self._log(spool, "weighed", before, spool.remaining_weight, f"scale {float(gross_weight):g} g")
        self._touch(spool)
        return spool

    @callback
    def async_consume(self, spool_id: str, grams: float) -> Spool:
        """Subtract used filament (never below zero)."""
        spool = self._require(spool_id)
        before = spool.remaining_weight
        spool.remaining_weight = max(0.0, spool.remaining_weight - float(grams))
        self._log(spool, "used", before, spool.remaining_weight, f"{float(grams):g} g")
        self._touch(spool)
        return spool

    @callback
    def async_delete(self, spool_id: str) -> Spool:
        """Remove a spool from the inventory."""
        spool = self._require(spool_id)
        self._log(spool, "deleted", spool.remaining_weight, None)
        del self._spools[spool_id]
        self._trash = [
            {**asdict(spool), "deleted_at": dt_util.utcnow().isoformat()},
            *[e for e in self._trash if e.get("id") != spool_id],
        ][:TRASH_MAX]
        self._alerts.pop(spool_id, None)
        persistent_notification.async_dismiss(self.hass, self._notification_id(spool_id))
        self._schedule_save()
        async_dispatcher_send(self.hass, SIGNAL_SPOOL_REMOVED, spool_id)
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return spool

    @callback
    def async_archive(self, spool_id: str, archived: bool = True) -> Spool:
        """Mark a spool as finished (kept as a record) or bring it back."""
        spool = self._require(spool_id)
        if spool.archived == archived:
            return spool
        spool.archived = archived
        self._log(spool, "archived" if archived else "unarchived", spool.remaining_weight, spool.remaining_weight)
        spool.archived_at = dt_util.utcnow().isoformat() if archived else ""
        if archived:
            spool.loaded = False
        spool.updated = dt_util.utcnow().isoformat()
        self._check_alert(spool, fire=False)  # archived = no alerts; restored = silent
        self._schedule_save()
        # an archived spool has no sensor; a restored one gets its sensor back
        async_dispatcher_send(
            self.hass, SIGNAL_SPOOL_REMOVED if archived else SIGNAL_SPOOL_ADDED, spool_id
        )
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return spool

    @callback
    def async_restore_deleted(self, spool_id: str) -> Spool:
        """Bring a deleted spool back from the trash."""
        entry = next((e for e in self._trash if e.get("id") == spool_id), None)
        if entry is None or spool_id in self._spools:
            raise _error("not_in_trash")
        data = {k: v for k, v in entry.items() if k != "deleted_at"}
        spool = Spool.from_dict(data)
        self._trash = [e for e in self._trash if e.get("id") != spool_id]
        self._spools[spool.id] = spool
        self._alerts[spool.id] = self._status(spool)
        self._log(spool, "restored", None, spool.remaining_weight)
        self._schedule_save()
        if not spool.archived:
            async_dispatcher_send(self.hass, SIGNAL_SPOOL_ADDED, spool.id)
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return spool

    @callback
    def async_rebuy(self, spool_id: str) -> Spool:
        """Add a new full spool like this one (bought again) and clear its reorder flag."""
        src = self._require(spool_id)
        now = dt_util.utcnow().isoformat()
        new = Spool(
            id=uuid.uuid4().hex,
            vendor=src.vendor,
            material=src.material,
            product=src.product,
            color_name=src.color_name,
            color_hex=src.color_hex,
            diameter=src.diameter,
            initial_weight=src.initial_weight,
            spool_weight=src.spool_weight,
            remaining_weight=src.initial_weight,
            price=src.price,
            refill=src.refill,
            location=src.location,
            created=now,
            updated=now,
        )
        src.reorder = False
        src.updated = now
        self._log(src, "bought another", None, None, "reorder flag cleared")
        self._log(new, "added", None, new.remaining_weight, "bought again")
        self._spools[new.id] = new
        self._alerts[new.id] = self._status(new)
        self._schedule_save()
        if not src.archived:
            async_dispatcher_send(self.hass, signal_spool_updated(src.id))
        async_dispatcher_send(self.hass, SIGNAL_SPOOL_ADDED, new.id)
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return new

    # ---- backup / restore ----------------------------------------------

    def export_data(self) -> dict[str, Any]:
        """Everything needed to rebuild the inventory elsewhere (a backup file)."""
        return {
            "format": EXPORT_FORMAT,
            "version": 1,
            "exported": dt_util.utcnow().isoformat(),
            "spools": [asdict(s) for s in self.spools],
            "settings": deepcopy(self._settings),
            "catalog": deepcopy(self._user_catalog),
            "history": deepcopy(self._history),
            "equipment": deepcopy(self.equipment.as_data()),
        }

    @staticmethod
    def _parse_spool(item: Any) -> Spool:
        spool = Spool.from_dict(item)
        if not (spool.id and spool.vendor and spool.material):
            raise ValueError("incomplete spool")
        for name in ("diameter", "initial_weight", "spool_weight", "remaining_weight"):
            setattr(spool, name, float(getattr(spool, name)))
        spool.remaining_weight = max(0.0, spool.remaining_weight)
        spool.loaded = bool(spool.loaded)
        spool.reorder = bool(spool.reorder)
        spool.refill = bool(spool.refill)
        spool.archived = bool(spool.archived)
        return spool

    async def async_import(self, data: dict[str, Any], replace: bool) -> dict[str, Any]:
        """Load a backup file: add what is missing, or replace everything."""
        if (
            not isinstance(data, dict)
            or data.get("format") != EXPORT_FORMAT
            or not isinstance(data.get("spools"), list)
        ):
            raise _error("import_invalid")
        parsed: dict[str, Spool] = {}
        skipped = 0
        for item in data["spools"]:
            try:
                spool = self._parse_spool(item)
            except (TypeError, ValueError, AttributeError):
                skipped += 1
                continue
            parsed[spool.id] = spool

        catalog = []
        for entry in data.get("catalog") or []:
            try:
                catalog.append(
                    {
                        "vendor": str(entry["vendor"]).strip(),
                        "material": str(entry["material"]).strip(),
                        "line": str(entry.get("line", "")).strip(),
                        "name": str(entry["name"]).strip(),
                        "hex": str(entry.get("hex", DEFAULT_COLOR_HEX)),
                        "weights": [float(w) for w in entry.get("weights", [DEFAULT_INITIAL_WEIGHT])],
                        **({"tare": float(entry["tare"])} if entry.get("tare") else {}),
                    }
                )
            except (KeyError, TypeError, ValueError, AttributeError):
                skipped += 1

        history = [
            {k: e.get(k) for k in ("t", "id", "name", "action", "before", "after", "note")}
            for e in (data.get("history") or [])
            if isinstance(e, dict) and e.get("id") and e.get("t") and e.get("action")
        ]
        if replace:
            # keep what is there now, in case the restore was a mistake
            await Store(self.hass, 1, PRE_IMPORT_KEY).async_save(self._data_to_save())
            for spool in list(self._spools.values()):
                persistent_notification.async_dismiss(self.hass, self._notification_id(spool.id))
                if not spool.archived:
                    async_dispatcher_send(self.hass, SIGNAL_SPOOL_REMOVED, spool.id)
            self._spools = dict(parsed)
            self._history = history[-HISTORY_MAX:]
            self.equipment.replace(data.get("equipment") or {})
            self._user_catalog = catalog[:MAX_USER_CATALOG]
            stored = data.get("settings")
            if isinstance(stored, dict):
                self.async_update_settings(
                    {k: stored[k] for k in ("low_threshold", "notify", "locations", "currency") if k in stored}
                )
            added = len(parsed)
            for spool in parsed.values():
                if not spool.archived:
                    async_dispatcher_send(self.hass, SIGNAL_SPOOL_ADDED, spool.id)
        else:
            fresh = {sid: s for sid, s in parsed.items() if sid not in self._spools}
            self._spools.update(fresh)
            self.equipment.merge(data.get("equipment") or {})
            seen = {(e["t"], e["id"], e["action"]) for e in self._history}
            self._history = sorted(
                [*self._history, *(e for e in history if (e["t"], e["id"], e["action"]) not in seen)],
                key=lambda e: e["t"],
            )[-HISTORY_MAX:]
            known = {self._catalog_key(e) for e in self._user_catalog}
            for entry in catalog:
                if self._catalog_key(entry) not in known and len(self._user_catalog) < MAX_USER_CATALOG:
                    self._user_catalog.append(entry)
            added = len(fresh)
            for spool in fresh.values():
                if not spool.archived:
                    async_dispatcher_send(self.hass, SIGNAL_SPOOL_ADDED, spool.id)
        # nothing imported raises alerts
        self._alerts = {s.id: self._status(s) for s in self._spools.values()}
        await self.async_flush()
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return {"added": added, "skipped": skipped, "replaced": replace}

    @callback
    def _touch(self, spool: Spool) -> None:
        spool.updated = dt_util.utcnow().isoformat()
        self._check_alert(spool)
        self._schedule_save()
        self._notify(spool.id)

    # ---- low / empty alerts ----------------------------------------------

    @staticmethod
    def _notification_id(spool_id: str) -> str:
        return f"{DOMAIN}_{spool_id}"

    @callback
    def _check_alert(self, spool: Spool, *, fire: bool = True) -> None:
        """Fire an event (and a notification) when a spool gets low or runs out."""
        new = self._status(spool)
        old = self._alerts.get(spool.id, "ok")
        self._alerts[spool.id] = new
        if new == old:
            return
        note_id = self._notification_id(spool.id)
        if new == "ok":
            persistent_notification.async_dismiss(self.hass, note_id)
            return
        if fire and _RANK[new] > _RANK[old]:
            self.hass.bus.async_fire(
                EVENT_EMPTY if new == "empty" else EVENT_LOW,
                {
                    "spool_id": spool.id,
                    "name": spool.display_name,
                    "remaining_weight": round(spool.remaining_weight, 1),
                    "threshold": self.low_threshold,
                    "location": spool.location,
                },
            )
        if not fire:
            return  # silent re-evaluation (threshold changed): no notification either
        if self._settings["notify"]:
            persistent_notification.async_create(
                self.hass,
                f"{spool.display_name}: "
                + ("empty." if new == "empty" else f"only {spool.remaining_weight:g} g left."),
                title="Filament empty" if new == "empty" else "Filament low",
                notification_id=note_id,
            )
        else:
            persistent_notification.async_dismiss(self.hass, note_id)

    # ---- settings -----------------------------------------------------------

    @callback
    def async_update_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Change the alert threshold, the notification switch or the location list."""
        if "low_threshold" in changes:
            self._settings["low_threshold"] = float(changes["low_threshold"])
        if "notify" in changes:
            self._settings["notify"] = bool(changes["notify"])
        if "currency" in changes:
            self._settings["currency"] = str(changes["currency"]).strip()[:8] or DEFAULT_SETTINGS["currency"]
        if "locations" in changes:
            seen: dict[str, str] = {}
            for name in changes["locations"]:
                if (name := str(name).strip()) and name.lower() not in seen:
                    seen[name.lower()] = name
            self._settings["locations"] = list(seen.values())[:30]
        if not self._settings["notify"]:
            for spool_id in self._spools:
                persistent_notification.async_dismiss(self.hass, self._notification_id(spool_id))
        # Re-evaluate every spool against the new threshold without raising alerts.
        for spool in self._spools.values():
            self._check_alert(spool, fire=False)
        self._schedule_save()
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return self._settings

    # ---- the user's own catalog -------------------------------------------

    @staticmethod
    def _catalog_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
        return tuple(  # type: ignore[return-value]
            str(entry.get(k, "")).strip().lower()
            for k in ("vendor", "material", "line", "name")
        )

    @callback
    def async_catalog_add(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Save (or replace) one catalog entry made from a custom spool."""
        clean = {
            "vendor": entry["vendor"].strip(),
            "material": entry["material"].strip(),
            "line": entry.get("line", "").strip(),
            "name": entry["name"].strip(),
            "hex": entry.get("hex", DEFAULT_COLOR_HEX),
            "weights": [float(w) for w in entry.get("weights", [DEFAULT_INITIAL_WEIGHT])]
            or [DEFAULT_INITIAL_WEIGHT],
        }
        if entry.get("tare"):
            clean["tare"] = float(entry["tare"])
        key = self._catalog_key(clean)
        kept = [e for e in self._user_catalog if self._catalog_key(e) != key]
        if len(kept) >= MAX_USER_CATALOG:
            raise _error("catalog_full")
        self._user_catalog = [*kept, clean]
        self._schedule_save()
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
        return clean

    @callback
    def async_catalog_remove(self, entry: dict[str, Any]) -> None:
        """Remove one entry from the user's catalog (no error if it is gone)."""
        key = self._catalog_key(entry)
        self._user_catalog = [e for e in self._user_catalog if self._catalog_key(e) != key]
        self._schedule_save()
        async_dispatcher_send(self.hass, SIGNAL_INVENTORY_CHANGED)
