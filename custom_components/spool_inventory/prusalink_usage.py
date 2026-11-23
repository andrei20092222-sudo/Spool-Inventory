"""Subtract filament from the loaded spool when the PrusaLink printer finishes a print.

This reuses the printer the user already added with Home Assistant's own PrusaLink
integration. Nothing is set up twice and nothing runs unless the switch in the settings
is on.

How it works:
  * a print starts      -> read the current job and the print file's slicer data once
                           ("filament used [g]"), remember which spool is loaded
  * the print finishes  -> subtract the whole estimate from that spool
  * cancelled or failed -> subtract the estimate scaled by the progress reached
The result is an estimate (the slicer's number), written to the history as "auto: ..."
so it can be undone with "Set back to" or corrected by weighing the spool.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .manager import SpoolManager
from .printfile import file_refs, from_job_meta, read_estimate

_LOGGER = logging.getLogger(__name__)
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]

PRUSALINK = "prusalink"
STATE_KEY = "_printer.state"
PROGRESS_KEY = "_job.progress"
MATERIAL_KEY = "_printer.telemetry.material"
NO_FILAMENT = "---"  # what the printer reports when nothing is loaded
BUSY = {"printing", "paused"}
ENDED = {"finished", "stopped", "error", "idle", "ready"}
# g/cm3, used only when the file gives a length but no weight
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PC": 1.20, "PA": 1.14}
DEFAULT_DENSITY = 1.25
RETRY_DELAYS = (10, 20, 40, 60, 120)  # seconds between tries while the print runs
MIN_GRAMS = 0.5  # below this nothing is subtracted


def prusalink_entry_ids(hass: HomeAssistant) -> list[str]:
    """Ids of the PrusaLink printers set up in Home Assistant."""
    return [e.entry_id for e in hass.config_entries.async_entries(PRUSALINK)]


class PrusaLinkTracker:
    """Follows prints on the printers of Home Assistant's PrusaLink integration."""

    def __init__(self, hass: HomeAssistant, manager: SpoolManager) -> None:
        """Initialize the tracker."""
        self.hass = hass
        self.manager = manager
        self._unsub: Any = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._timers: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        """Whether the user switched the feature on."""
        return bool(self.manager.settings.get("prusalink_auto"))

    @callback
    def start(self) -> None:
        """Start listening (does nothing until the setting is on)."""
        self._unsub = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._on_state, event_filter=self._filter
        )
        self.hass.async_create_task(self.async_resume())

    @callback
    def stop(self) -> None:
        """Stop listening."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        for entry_id in list(self._timers):
            self._cancel_retry(entry_id)

    # ---- events ------------------------------------------------------------

    @callback
    def _filter(self, data: EventStateChangedData) -> bool:
        ent = er.async_get(self.hass).async_get(data["entity_id"])
        return bool(
            ent
            and ent.platform == PRUSALINK
            and ent.unique_id.endswith((STATE_KEY, PROGRESS_KEY, MATERIAL_KEY))
        )

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        if (new := event.data["new_state"]) is None:
            return
        ent = er.async_get(self.hass).async_get(event.data["entity_id"])
        if ent is None or not ent.config_entry_id:
            return
        entry_id = ent.config_entry_id
        if ent.unique_id.endswith(MATERIAL_KEY):
            self._on_material(entry_id, event.data["old_state"], new.state)
            return
        if not self.enabled:
            return
        if ent.unique_id.endswith(PROGRESS_KEY):
            self._note_progress(entry_id, new.state)
        elif new.state == "printing":
            if entry_id not in self.manager.auto_jobs:
                self.hass.async_create_task(self.async_open(entry_id))
        elif new.state in ENDED and entry_id in self.manager.auto_jobs:
            self.hass.async_create_task(self.async_close(entry_id, new.state))

    def _on_material(self, entry_id: str, old: Any, new: str) -> None:
        """Filament was unloaded from the printer: forget which spool was loaded.

        Only a real change from a material to "---" counts. "unavailable" (printer off,
        Home Assistant restarting) and anything while printing are ignored.
        """
        if not self.manager.settings.get("prusalink_unload") or new != NO_FILAMENT:
            return
        if old is None or old.state in (NO_FILAMENT, "", "unavailable", "unknown"):
            return
        if self._printer_state(er.async_get(self.hass), entry_id) in BUSY:
            return
        self.manager.async_clear_loaded()

    def _note_progress(self, entry_id: str, value: str) -> None:
        job = self.manager.auto_jobs.get(entry_id)
        try:
            progress = float(value)
        except (TypeError, ValueError):
            return
        if job is None:
            return
        job["progress"] = progress
        if progress - job.get("saved_progress", 0) >= 10:  # not on every poll: easy on the SD card
            job["saved_progress"] = progress
            self.manager.save_tracking()

    async def async_resume(self) -> None:
        """After a restart: pick up a print that is running right now."""
        if not self.enabled:
            return
        registry = er.async_get(self.hass)
        for entry_id in prusalink_entry_ids(self.hass):
            if entry_id in self.manager.auto_jobs:
                # a record from before the restart: close it if the print has ended meanwhile
                state = self._printer_state(registry, entry_id)
                if state in ENDED:
                    await self.async_close(entry_id, state)
                else:
                    job = self.manager.auto_jobs[entry_id]
                    if job.get("grams") is None and not job.get("gave_up"):
                        self._schedule_retry(entry_id, 10)
            elif self._printer_state(registry, entry_id) == "printing":
                await self.async_open(entry_id)

    def _printer_state(self, registry: er.EntityRegistry, entry_id: str) -> str | None:
        for ent in er.async_entries_for_config_entry(registry, entry_id):
            if ent.unique_id.endswith(STATE_KEY) and (st := self.hass.states.get(ent.entity_id)):
                return st.state
        return None

    # ---- the print starts ------------------------------------------------------

    def _lock(self, entry_id: str) -> asyncio.Lock:
        return self._locks.setdefault(entry_id, asyncio.Lock())

    def _client(self, entry_id: str) -> Any:
        from pyprusalink import PrusaLink  # noqa: PLC0415  # only present when PrusaLink is installed

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise RuntimeError("PrusaLink entry not found")
        return PrusaLink(
            get_async_client(self.hass),
            entry.data["host"],
            entry.data["username"],
            entry.data["password"],
        )

    async def _read_meta(self, entry_id: str, refs: list[str]) -> dict[str, Any]:
        """Read the filament estimate from the print file on the printer."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise RuntimeError("PrusaLink entry not found")
        return await read_estimate(
            self.hass, entry.data["host"], entry.data["username"], entry.data["password"], refs
        )

    def loaded_spool(self) -> str | None:
        """The one spool marked as loaded (None when there are none or several)."""
        loaded = [s for s in self.manager.active_spools if s.loaded]
        return loaded[0].id if len(loaded) == 1 else None

    async def async_open(self, entry_id: str) -> None:
        """Start following the print that just started and read its filament estimate."""
        async with self._lock(entry_id):
            if entry_id in self.manager.auto_jobs:
                return
            started = dt_util.utcnow().isoformat()
            record = {
                "key": f"{entry_id}:{started}",
                "file": "print",
                "grams": None,
                "spool_id": self.loaded_spool(),
                "started": started,
                "progress": 0.0,
                "saved_progress": 0,
                "tries": 0,
            }
            self.manager.auto_jobs[entry_id] = record
            self.manager.save_tracking()
            await self._attempt(entry_id, record)

    async def _attempt(self, entry_id: str, record: dict[str, Any]) -> None:
        """Try to learn the grams of the print (the lock is held by the caller).

        Right when a print starts, the printer may not report the file or its numbers yet,
        so this is repeated a few times while the print runs before giving up.
        """
        record["tries"] = record.get("tries", 0) + 1
        reason = ""
        try:
            job = await self._client(entry_id).get_job()
            if not job or not job.get("file"):
                reason = "the printer does not report the file yet"
            else:
                file = job["file"]
                name = file.get("display_name") or file.get("name") or "print"
                key = f"{job['id']}:{name}"
                if key in self.manager.auto_done:  # already subtracted (for example after a restart)
                    self.manager.auto_jobs.pop(entry_id, None)
                    self.manager.save_tracking()
                    return
                record["key"], record["file"] = key, name
                record["progress"] = max(float(record.get("progress") or 0), float(job.get("progress") or 0))
                record["refs"] = file_refs(file)
                _LOGGER.debug("PrusaLink job file: %s", file)
                # the printer often reports the numbers with the job; the file is the fallback
                meta = from_job_meta(file.get("meta"))
                if "filament_used_g" not in meta and "filament_used_mm" not in meta and not meta.get("multi"):
                    meta = await self._read_meta(entry_id, record["refs"])
                record["grams"] = self._grams(meta, record.get("spool_id") or self.loaded_spool())
                if record["grams"] is None:
                    reason = (
                        "this is a multi-material print, which is not supported yet"
                        if meta.get("multi")
                        else "the file has no filament information"
                    )
                    if meta.get("multi"):
                        record["tries"] = 99  # retrying will not change that
        except Exception as err:  # noqa: BLE001
            reason = f"could not read the file ({err})"
        self.manager.save_tracking()
        if record["grams"] is not None:
            self._cancel_retry(entry_id)
            if record.get("spool_id") is None and self.loaded_spool() is None:
                self._notify(entry_id, f"“{record['file']}” started but no single spool is marked as loaded. Mark one before it ends, or the filament will not be subtracted.")
            return
        record["reason"] = reason
        if record["tries"] > len(RETRY_DELAYS):
            record["gave_up"] = True
            if record["tries"] >= 99:  # multi-material: the end of the print will not change that, so say it now
                self._notify(entry_id, f"“{record['file']}”: {reason}. Nothing will be subtracted automatically for this print.")
            else:
                # Some printers only give out the file once the print is over. The file is read again at the end
                # and a notification is only shown if that fails too, so there is no alarm here.
                _LOGGER.info("%s: %s. Trying again when the print ends.", record["file"], reason)
            return
        self._schedule_retry(entry_id, RETRY_DELAYS[record["tries"] - 1])

    @callback
    def _schedule_retry(self, entry_id: str, delay: float) -> None:
        self._cancel_retry(entry_id)

        @callback
        def _fire(_now: Any) -> None:
            self._timers.pop(entry_id, None)
            self.hass.async_create_task(self._retry(entry_id))

        self._timers[entry_id] = async_call_later(self.hass, delay, _fire)

    @callback
    def _cancel_retry(self, entry_id: str) -> None:
        if cancel := self._timers.pop(entry_id, None):
            cancel()

    async def _retry(self, entry_id: str) -> None:
        async with self._lock(entry_id):
            record = self.manager.auto_jobs.get(entry_id)
            if record and record.get("grams") is None and not record.get("gave_up"):
                await self._attempt(entry_id, record)

    def _grams(self, meta: dict[str, Any], spool_id: str | None) -> float | None:
        if (g := meta.get("filament_used_g")) is not None:
            return float(g)
        if (mm := meta.get("filament_used_mm")) is not None:
            spool = self.manager.get(spool_id) if spool_id else None
            diameter = spool.diameter if spool else 1.75
            density = DENSITY.get((spool.material if spool else "").upper(), DEFAULT_DENSITY)
            radius_cm = diameter / 20
            return float(mm) / 10 * 3.14159265 * radius_cm**2 * density
        return None

    # ---- the print ends ----------------------------------------------------------

    async def async_close(self, entry_id: str, state: str) -> None:
        """Subtract the filament for the print that just ended."""
        async with self._lock(entry_id):
            job = self.manager.auto_jobs.pop(entry_id, None)
            if not job:
                return
            self.manager.save_tracking()
            self._cancel_retry(entry_id)
            key = job["key"]
            if key in self.manager.auto_done:
                return
            if job.get("grams") is None and job.get("refs"):  # one last look at the file
                try:
                    job["grams"] = self._grams(await self._read_meta(entry_id, job["refs"]), job.get("spool_id"))
                except Exception as err:  # noqa: BLE001
                    job["reason"] = f"could not read the file ({err})"
            if job.get("grams") is None:
                if not (job.get("gave_up") and job.get("tries", 0) >= 99):  # multi-material was already announced
                    self._notify(entry_id, f"“{job['file']}”: {job.get('reason') or 'no filament information'}. Nothing was subtracted for this print. Use “Used in printer” to subtract it by hand.")
                return
            progress = float(job.get("progress") or 0)
            full = state == "finished" or (state in ("idle", "ready") and progress >= 99)
            fraction = 1.0 if full else max(0.0, min(progress, 100.0)) / 100
            grams = round(job["grams"] * fraction, 1)
            self.manager.auto_done.append(key)
            del self.manager.auto_done[:-100]
            spool_id = job.get("spool_id") or self.loaded_spool()
            spool = self.manager.get(spool_id) if spool_id else None
            if spool is None or spool.archived:
                self._notify(entry_id, f"“{job['file']}” used about {grams:g} g, but there was no spool to subtract it from. Nothing was changed.")
                return
            if grams < MIN_GRAMS:
                return
            note = f"{job['file']}, {grams:g} g, estimate"
            if not full:
                note += f", stopped at {progress:g}%"
            self.manager.async_auto_use(spool.id, grams, note)

    @callback
    def _notify(self, entry_id: str, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            f"{message}\n\n(Spool Inventory {VERSION})",
            title="Filament: automatic subtraction",
            notification_id=f"{DOMAIN}_prusalink_{entry_id}",
        )
