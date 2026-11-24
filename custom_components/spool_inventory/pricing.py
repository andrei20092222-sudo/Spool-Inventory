"""Price calculator: what a print costs and what to ask for it (v1.1.0).

The maths is plain: filament + electricity + machine wear + your time + extras, plus a failure allowance, plus a
markup. Everything the person types (rates, machines, quotes) is stored with the spools and never leaves the
installation. Defaults are neutral zeros, not anybody's real prices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_INVENTORY_CHANGED

if TYPE_CHECKING:
    from .manager import SpoolManager

MAX_MACHINES = 10
MAX_QUOTES = 500
MAX_FILAMENTS = 4
STATUSES = ("draft", "sent", "paid")

DEFAULT_PRICING = {
    "energy_cost": 0.0,  # per kWh
    "labor_rate": 0.0,  # per hour
    "failure_pct": 5.0,  # allowance for failed prints, on top of the subtotal
    "markup_pct": 15.0,  # the fixed markup price
    "markup_small_pct": 35.0,  # suggested markup while the cost is at or below the threshold
    "markup_large_pct": 20.0,  # suggested markup above the threshold (big jobs earn a smaller percentage)
    "large_threshold": 100.0,  # in your currency
}


def _err(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def _text(value: Any, limit: int = 80) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _num(value: Any, default: float = 0.0, high: float = 1_000_000.0) -> float:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return min(max(number, 0.0), high)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def depreciation_per_hour(machine: dict[str, Any]) -> float:
    """Machine price plus service costs over its working life."""
    life = machine.get("life_hours") or 0
    return (machine.get("price", 0) + machine.get("service", 0)) / life if life > 0 else 0.0


def calculate(settings: dict[str, Any], machine: dict[str, Any] | None, raw: dict[str, Any]) -> dict[str, Any]:
    """Cost breakdown for one job. Pure function: same input, same answer."""
    cfg = {**DEFAULT_PRICING, **{k: _num(v) for k, v in settings.items() if k in DEFAULT_PRICING}}
    hours = _num(raw.get("hours"), high=10000)
    filament = 0.0
    grams = 0.0
    for f in (raw.get("filaments") or [])[:MAX_FILAMENTS]:
        if not isinstance(f, dict):
            continue
        g = _num(f.get("grams"), high=100000)
        filament += g / 1000 * _num(f.get("price_per_kg"))
        grams += g
    electricity = hours * (machine.get("kwh_per_h", 0) if machine else 0) * cfg["energy_cost"]
    depreciation = hours * (depreciation_per_hour(machine) if machine else 0)
    prep = _num(raw.get("prep_min"), high=100000) / 60 * cfg["labor_rate"]
    post = _num(raw.get("post_min"), high=100000) / 60 * cfg["labor_rate"]
    extras = _num(raw.get("consumables")) + _num(raw.get("extra"))
    design = _num(raw.get("design"))
    subtotal = design + filament + electricity + depreciation + prep + post + extras
    with_failures = subtotal * (1 + cfg["failure_pct"] / 100)
    suggest_pct = cfg["markup_large_pct"] if with_failures > cfg["large_threshold"] else cfg["markup_small_pct"]
    quoted = _num(raw.get("quoted"))
    shipping = _num(raw.get("shipping"))
    return {
        "grams": round(grams, 1),
        "design": round(design, 2),
        "filament": round(filament, 2),
        "electricity": round(electricity, 2),
        "depreciation": round(depreciation, 2),
        "preparation": round(prep, 2),
        "post_processing": round(post, 2),
        "extras": round(extras, 2),
        "subtotal": round(subtotal, 2),
        "with_failures": round(with_failures, 2),
        "suggested_pct": suggest_pct,
        "suggested": round(with_failures * (1 + suggest_pct / 100), 2),
        "markup_price": round(with_failures * (1 + cfg["markup_pct"] / 100), 2),
        "quoted": round(quoted, 2),
        "shipping": round(shipping, 2),
        "total": round(quoted + shipping, 2),
        "profit": round(quoted - with_failures, 2) if quoted else None,
    }


class Pricing:
    """Rates, machines and saved quotes."""

    def __init__(self, manager: SpoolManager) -> None:
        self._m = manager
        self.settings: dict[str, float] = dict(DEFAULT_PRICING)
        self.machines: list[dict[str, Any]] = []
        self.quotes: list[dict[str, Any]] = []

    # ---- persistence ------------------------------------------------------

    def as_data(self) -> dict[str, Any]:
        return {"settings": self.settings, "machines": self.machines, "quotes": self.quotes}

    def load(self, data: dict[str, Any]) -> None:
        stored = data.get("settings")
        self.settings = {k: (_num(stored[k]) if isinstance(stored, dict) and k in stored else v) for k, v in DEFAULT_PRICING.items()}
        self.machines = [m for m in (self._clean_machine(x) for x in _rows(data.get("machines"))) if m][:MAX_MACHINES]
        self.quotes = [q for q in (self._clean_quote(x) for x in _rows(data.get("quotes"))) if q][:MAX_QUOTES]

    def replace(self, data: dict[str, Any]) -> None:
        self.load(data)

    def merge(self, data: dict[str, Any]) -> None:
        """Add machines and quotes that are not here yet (by id); the rates stay as they are."""
        other = Pricing(self._m)
        other.load(data)
        for mine, theirs, cap in ((self.machines, other.machines, MAX_MACHINES), (self.quotes, other.quotes, MAX_QUOTES)):
            known = {r["id"] for r in mine}
            mine.extend(r for r in theirs if r["id"] not in known and len(mine) < cap)

    @staticmethod
    def _clean_machine(raw: dict[str, Any]) -> dict[str, Any] | None:
        name = _text(raw.get("name"), 60)
        if not name or not raw.get("id"):
            return None
        return {
            "id": str(raw["id"]), "name": name, "price": round(_num(raw.get("price")), 2),
            "service": round(_num(raw.get("service")), 2), "life_hours": round(_num(raw.get("life_hours"), 10000, 1_000_000), 1),
            "kwh_per_h": round(_num(raw.get("kwh_per_h"), 0.0, 100), 3),
        }

    def _clean_quote(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if not raw.get("id"):
            return None
        filaments = []
        for f in (raw.get("filaments") or [])[:MAX_FILAMENTS]:
            if isinstance(f, dict):
                filaments.append({"spool_id": _text(f.get("spool_id"), 40), "name": _text(f.get("name"), 120),
                                  "grams": round(_num(f.get("grams"), high=100000), 1), "price_per_kg": round(_num(f.get("price_per_kg")), 2)})
        status = raw.get("status") if raw.get("status") in STATUSES else "draft"
        quote = {
            "id": str(raw["id"]), "created": _text(raw.get("created"), 40), "updated": _text(raw.get("updated"), 40),
            "customer": _text(raw.get("customer"), 80), "description": _text(raw.get("description"), 200), "status": status,
            "machine_id": _text(raw.get("machine_id"), 40), "filaments": filaments,
            **{k: round(_num(raw.get(k), high=100000 if k.endswith("_min") or k == "hours" else 1_000_000), 4 if k == "hours" else 2)
               for k in ("hours", "prep_min", "post_min", "consumables", "extra", "design", "quoted", "shipping")},
        }
        quote["result"] = calculate(self.settings, self._machine_or_none(quote["machine_id"]), quote)
        return quote

    # ---- queries ----------------------------------------------------------

    def _machine_or_none(self, machine_id: str) -> dict[str, Any] | None:
        return next((m for m in self.machines if m["id"] == machine_id), None)

    def payload(self) -> dict[str, Any]:
        return {
            "settings": dict(self.settings),
            "machines": [{**m, "depreciation_per_h": round(depreciation_per_hour(m), 4)} for m in self.machines],
            "quotes": sorted(self.quotes, key=lambda q: q["updated"] or q["created"], reverse=True),
        }

    def calculate(self, raw: dict[str, Any]) -> dict[str, Any]:
        return calculate(self.settings, self._machine_or_none(str(raw.get("machine_id") or "")), raw)

    @callback
    def _changed(self) -> None:
        self._m._schedule_save()  # noqa: SLF001
        async_dispatcher_send(self._m.hass, SIGNAL_INVENTORY_CHANGED)

    # ---- changes ----------------------------------------------------------

    @callback
    def update_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        for key in DEFAULT_PRICING:
            if key in changes:
                self.settings[key] = round(_num(changes[key], high=100000), 4)
        # Quotes keep their saved numbers until they are opened and saved again; recompute the shown result.
        for quote in self.quotes:
            quote["result"] = calculate(self.settings, self._machine_or_none(quote["machine_id"]), quote)
        self._changed()
        return dict(self.settings)

    @callback
    def machine_add(self, data: dict[str, Any]) -> dict[str, Any]:
        if len(self.machines) >= MAX_MACHINES:
            raise _err("too_many_machines")
        machine = self._clean_machine({**data, "id": uuid.uuid4().hex[:12]})
        if machine is None:
            raise _err("machine_not_found")
        self.machines.append(machine)
        self._changed()
        return machine

    @callback
    def machine_update(self, machine_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        machine = self._machine_or_none(machine_id)
        if machine is None:
            raise _err("machine_not_found")
        cleaned = self._clean_machine({**machine, **{k: v for k, v in changes.items() if k != "id"}})
        if cleaned is None:
            raise _err("machine_not_found")
        machine.update(cleaned)
        for quote in self.quotes:
            if quote["machine_id"] == machine_id:
                quote["result"] = calculate(self.settings, machine, quote)
        self._changed()
        return machine

    @callback
    def machine_delete(self, machine_id: str) -> None:
        if self._machine_or_none(machine_id) is None:
            raise _err("machine_not_found")
        self.machines = [m for m in self.machines if m["id"] != machine_id]
        self._changed()  # quotes keep their saved result; they just lose the live link to the machine

    @callback
    def quote_save(self, data: dict[str, Any], quote_id: str | None = None) -> dict[str, Any]:
        now = dt_util.utcnow().isoformat()
        existing = next((q for q in self.quotes if q["id"] == quote_id), None) if quote_id else None
        if quote_id and existing is None:
            raise _err("quote_not_found")
        if existing is None and len(self.quotes) >= MAX_QUOTES:
            raise _err("too_many_quotes")
        quote = self._clean_quote({**data, "id": quote_id or uuid.uuid4().hex[:12],
                                   "created": existing["created"] if existing else now, "updated": now})
        if quote is None:
            raise _err("quote_not_found")
        if existing is None:
            self.quotes.append(quote)
        else:
            existing.clear()
            existing.update(quote)
        self._m.log_raw(quote["id"], quote["customer"] or quote["description"] or "Quote", "quote_saved", f'{quote["result"]["with_failures"]}')
        self._changed()
        return quote

    @callback
    def quote_delete(self, quote_id: str) -> None:
        if not any(q["id"] == quote_id for q in self.quotes):
            raise _err("quote_not_found")
        self.quotes = [q for q in self.quotes if q["id"] != quote_id]
        self._changed()
