"""3D printers, their maintenance tasks, and parts / consumables (v0.6.0)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.components import persistent_notification
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_ITEM_LOW,
    EVENT_TASK_DUE,
    MAX_ITEMS,
    MAX_PRINTERS,
    MAX_TASKS,
    SIGNAL_INVENTORY_CHANGED,
)

if TYPE_CHECKING:
    from .manager import SpoolManager

SOON_DAYS = 7  # a task is "soon" when it is due within this many days

# Offered when a printer is added; everything can be changed or deleted afterwards.
STARTER_TASKS: list[tuple[str, int]] = [
    ("Wipe the print sheet with IPA", 7),
    ("Clean the nozzle and the area around it", 30),
    ("Lubricate the rods / rails", 90),
    ("Check belt tension", 90),
    ("Clean the fans and filters", 90),
    ("General check: screws, cables, wear", 180),
]


def _err(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def _text(value: Any, limit: int = 80) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _today() -> date:
    return dt_util.now().date()


def _parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class Equipment:
    """Printers, maintenance tasks and items. Stored together with the spools."""

    def __init__(self, manager: SpoolManager) -> None:
        self._m = manager
        self.printers: list[dict[str, Any]] = []
        self.tasks: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self._task_state: dict[str, str] = {}
        self._item_state: dict[str, bool] = {}

    # ---- persistence ------------------------------------------------------

    def as_data(self) -> dict[str, Any]:
        return {"printers": self.printers, "tasks": self.tasks, "items": self.items}

    def load(self, data: dict[str, Any]) -> None:
        """Read stored data; unreadable rows are skipped."""
        self.printers = [p for p in (self._clean_printer(x) for x in _rows(data.get("printers"))) if p]
        self.tasks = [t for t in (self._clean_task(x) for x in _rows(data.get("tasks"))) if t]
        ids = {p["id"] for p in self.printers}
        self.tasks = [t for t in self.tasks if t["printer_id"] in ids]
        self.items = [i for i in (self._clean_item(x) for x in _rows(data.get("items"))) if i]
        for item in self.items:
            if item["printer_id"] not in ids:
                item["printer_id"] = ""
        self._task_state = {t["id"]: self._task_status(t)["state"] for t in self.tasks}
        self._item_state = {i["id"]: self._is_low(i) for i in self.items}
        self.check_tasks(fire=False)

    def replace(self, data: dict[str, Any]) -> None:
        self.load(data)

    def merge(self, data: dict[str, Any]) -> None:
        """Add printers, tasks and items that are not here yet (by id)."""
        other = Equipment(self._m)
        other.load(data)
        for mine, theirs in ((self.printers, other.printers), (self.tasks, other.tasks), (self.items, other.items)):
            known = {r["id"] for r in mine}
            mine.extend(r for r in theirs if r["id"] not in known)
        self.load(self.as_data())

    # ---- cleaning ---------------------------------------------------------

    @staticmethod
    def _clean_printer(raw: dict[str, Any]) -> dict[str, Any] | None:
        name = _text(raw.get("name"), 60)
        if not name or not raw.get("id"):
            return None
        return {"id": str(raw["id"]), "name": name, "model": _text(raw.get("model"), 60), "notes": _text(raw.get("notes"), 300)}

    @staticmethod
    def _clean_task(raw: dict[str, Any]) -> dict[str, Any] | None:
        name = _text(raw.get("name"), 80)
        try:
            interval = int(raw.get("interval_days"))
        except (TypeError, ValueError):
            return None
        if not name or not raw.get("id") or not raw.get("printer_id") or not 1 <= interval <= 3650:
            return None
        last = _parse_day(raw.get("last_done")) or _today()
        return {
            "id": str(raw["id"]), "printer_id": str(raw["printer_id"]), "name": name,
            "interval_days": interval, "last_done": last.isoformat(), "notes": _text(raw.get("notes"), 300),
        }

    @staticmethod
    def _clean_item(raw: dict[str, Any]) -> dict[str, Any] | None:
        name = _text(raw.get("name"), 80)
        try:
            quantity = max(0.0, float(raw.get("quantity", 0)))
            low_at = max(0.0, float(raw.get("low_at", 0) or 0))
        except (TypeError, ValueError):
            return None
        if not name or not raw.get("id"):
            return None
        return {
            "id": str(raw["id"]), "printer_id": _text(raw.get("printer_id"), 40), "category": _text(raw.get("category"), 40) or "Other",
            "name": name, "quantity": round(quantity, 2), "unit": _text(raw.get("unit"), 12), "low_at": round(low_at, 2),
            "notes": _text(raw.get("notes"), 300), "reorder": bool(raw.get("reorder", False)),
        }

    # ---- queries ----------------------------------------------------------

    @staticmethod
    def _is_low(item: dict[str, Any]) -> bool:
        return item["low_at"] > 0 and item["quantity"] <= item["low_at"]

    def _task_status(self, task: dict[str, Any]) -> dict[str, Any]:
        last = _parse_day(task["last_done"]) or _today()
        due = last + timedelta(days=task["interval_days"])
        left = (due - _today()).days
        state = "overdue" if left < 0 else "soon" if left <= SOON_DAYS else "ok"
        return {"due_date": due.isoformat(), "days_left": left, "state": state}

    def payload(self) -> dict[str, Any]:
        """What the panel shows: tasks with their due dates, items with a low flag."""
        return {
            "printers": [dict(p) for p in self.printers],
            "tasks": [{**t, **self._task_status(t)} for t in self.tasks],
            "items": [{**i, "low": self._is_low(i), "to_reorder": i["reorder"] or self._is_low(i)} for i in self.items],
        }

    def overdue(self) -> list[dict[str, Any]]:
        return [{**t, **s} for t in self.tasks if (s := self._task_status(t))["state"] == "overdue"]

    def low_items(self) -> list[dict[str, Any]]:
        return [i for i in self.items if self._is_low(i) or i["reorder"]]

    # ---- helpers ----------------------------------------------------------

    def _printer(self, printer_id: str) -> dict[str, Any]:
        for p in self.printers:
            if p["id"] == printer_id:
                return p
        raise _err("printer_not_found")

    def _task(self, task_id: str) -> dict[str, Any]:
        for t in self.tasks:
            if t["id"] == task_id:
                return t
        raise _err("task_not_found")

    def _item(self, item_id: str) -> dict[str, Any]:
        for i in self.items:
            if i["id"] == item_id:
                return i
        raise _err("item_not_found")

    @callback
    def _changed(self) -> None:
        self._m._schedule_save()  # noqa: SLF001
        async_dispatcher_send(self._m.hass, SIGNAL_INVENTORY_CHANGED)

    def _log(self, ident: str, name: str, action: str, note: str = "") -> None:
        self._m.log_raw(ident, name, action, note)

    # ---- printers ---------------------------------------------------------

    @callback
    def printer_add(self, name: str, model: str = "", starter: bool = False) -> dict[str, Any]:
        if len(self.printers) >= MAX_PRINTERS:
            raise _err("equipment_full")
        printer = self._clean_printer({"id": uuid.uuid4().hex, "name": name, "model": model})
        if printer is None:
            raise _err("name_required")
        self.printers.append(printer)
        if starter:
            for title, days in STARTER_TASKS:
                self.task_add(printer["id"], title, days, quiet=True)
        self._log(printer["id"], printer["name"], "printer added")
        self._changed()
        return printer

    @callback
    def printer_update(self, printer_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        printer = self._printer(printer_id)
        for key in ("name", "model", "notes"):
            if key in changes:
                value = _text(changes[key], 300 if key == "notes" else 60)
                if key == "name" and not value:
                    raise _err("name_required")
                printer[key] = value
        self._changed()
        return printer

    @callback
    def printer_delete(self, printer_id: str) -> None:
        printer = self._printer(printer_id)
        for task in [t for t in self.tasks if t["printer_id"] == printer_id]:
            self._dismiss(f"task_{task['id']}")
            self._task_state.pop(task["id"], None)
        self.tasks = [t for t in self.tasks if t["printer_id"] != printer_id]
        for item in self.items:
            if item["printer_id"] == printer_id:
                item["printer_id"] = ""
        self.printers = [p for p in self.printers if p["id"] != printer_id]
        self._log(printer["id"], printer["name"], "printer deleted")
        self._changed()

    # ---- maintenance tasks ------------------------------------------------

    @callback
    def task_add(self, printer_id: str, name: str, interval_days: int, last_done: str | None = None, notes: str = "", quiet: bool = False) -> dict[str, Any]:
        self._printer(printer_id)
        if len(self.tasks) >= MAX_TASKS:
            raise _err("equipment_full")
        task = self._clean_task({
            "id": uuid.uuid4().hex, "printer_id": printer_id, "name": name, "interval_days": interval_days,
            "last_done": last_done or _today().isoformat(), "notes": notes,
        })
        if task is None:
            raise _err("task_invalid")
        self.tasks.append(task)
        self._task_state[task["id"]] = self._task_status(task)["state"]
        if not quiet:
            self._log(task["id"], task["name"], "task added", f"every {task['interval_days']} days")
            self._changed()
            self.check_tasks(fire=False)
        return task

    @callback
    def task_update(self, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        task = self._task(task_id)
        candidate = {**task, **{k: v for k, v in changes.items() if k in ("name", "interval_days", "last_done", "notes")}}
        cleaned = self._clean_task(candidate)
        if cleaned is None:
            raise _err("task_invalid")
        task.update(cleaned)
        self.check_tasks(fire=False)
        self._changed()
        return task

    @callback
    def task_done(self, task_id: str, day: str | None = None, note: str = "") -> dict[str, Any]:
        """Mark a task as done (today unless a date is given)."""
        task = self._task(task_id)
        done = _parse_day(day) if day else _today()
        if done is None or done > _today():
            raise _err("task_invalid")
        task["last_done"] = done.isoformat()
        self._log(task["id"], task["name"], "maintenance done", note)
        self.check_tasks(fire=False)
        self._changed()
        return task

    @callback
    def task_delete(self, task_id: str) -> None:
        self._task(task_id)  # raises when it does not exist
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self._task_state.pop(task_id, None)
        self._dismiss(f"task_{task_id}")
        self._changed()

    # ---- parts / consumables ---------------------------------------------

    @callback
    def item_add(self, data: dict[str, Any]) -> dict[str, Any]:
        if len(self.items) >= MAX_ITEMS:
            raise _err("equipment_full")
        if data.get("printer_id"):
            self._printer(data["printer_id"])
        item = self._clean_item({**data, "id": uuid.uuid4().hex})
        if item is None:
            raise _err("item_invalid")
        self.items.append(item)
        self._item_state[item["id"]] = self._is_low(item)  # a new item never raises an alert
        self._log(item["id"], item["name"], "item added", f"{item['quantity']:g} {item['unit']}".strip())
        self._changed()
        return item

    @callback
    def item_update(self, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        item = self._item(item_id)
        if changes.get("printer_id"):
            self._printer(changes["printer_id"])
        before = item["quantity"]
        cleaned = self._clean_item({**item, **{k: v for k, v in changes.items() if k != "id"}})
        if cleaned is None:
            raise _err("item_invalid")
        item.update(cleaned)
        if abs(item["quantity"] - before) > 0.004:
            self._log(item["id"], item["name"], "item changed", f"{before:g} -> {item['quantity']:g} {item['unit']}".strip())
        self._check_item(item)
        self._changed()
        return item

    @callback
    def item_adjust(self, item_id: str, delta: float) -> dict[str, Any]:
        """Add (positive) or use up (negative) some of an item."""
        item = self._item(item_id)
        return self.item_update(item_id, {"quantity": max(0.0, item["quantity"] + float(delta))})

    @callback
    def item_delete(self, item_id: str) -> None:
        item = self._item(item_id)
        self.items = [i for i in self.items if i["id"] != item_id]
        self._item_state.pop(item_id, None)
        self._dismiss(f"item_{item_id}")
        self._log(item["id"], item["name"], "item deleted")
        self._changed()

    # ---- alerts -----------------------------------------------------------

    def _dismiss(self, key: str) -> None:
        persistent_notification.async_dismiss(self._m.hass, f"{DOMAIN}_{key}")

    def _printer_name(self, printer_id: str) -> str:
        return next((p["name"] for p in self.printers if p["id"] == printer_id), "")

    def _check_item(self, item: dict[str, Any]) -> None:
        low = self._is_low(item)
        was = self._item_state.get(item["id"], False)
        self._item_state[item["id"]] = low
        if not low:
            self._dismiss(f"item_{item['id']}")
            return
        if was:
            return
        self._m.hass.bus.async_fire(EVENT_ITEM_LOW, {
            "item_id": item["id"], "name": item["name"], "quantity": item["quantity"], "low_at": item["low_at"], "unit": item["unit"],
        })
        if self._m.settings["notify"]:
            persistent_notification.async_create(
                self._m.hass, f"{item['name']}: {item['quantity']:g} {item['unit']} left, time to reorder.".replace("  ", " "),
                title="Running low", notification_id=f"{DOMAIN}_item_{item['id']}",
            )

    @callback
    def check_tasks(self, fire: bool = True) -> None:
        """Called at start and every hour: keep notifications in line and fire an event for newly overdue tasks."""
        notify = self._m.settings["notify"]
        for task in self.tasks:
            status = self._task_status(task)
            new, old = status["state"], self._task_state.get(task["id"], "ok")
            self._task_state[task["id"]] = new
            key = f"{DOMAIN}_task_{task['id']}"
            if new != "overdue":
                persistent_notification.async_dismiss(self._m.hass, key)
                continue
            if fire and old != "overdue":
                self._m.hass.bus.async_fire(EVENT_TASK_DUE, {
                    "task_id": task["id"], "name": task["name"], "printer": self._printer_name(task["printer_id"]),
                    "days_overdue": -status["days_left"],
                })
            if notify:
                persistent_notification.async_create(
                    self._m.hass,
                    f"{self._printer_name(task['printer_id'])}: {task['name']} is overdue by {-status['days_left']} days.",
                    title="Maintenance due", notification_id=key,
                )
            else:
                persistent_notification.async_dismiss(self._m.hass, key)
        if fire:
            async_dispatcher_send(self._m.hass, SIGNAL_INVENTORY_CHANGED)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []
