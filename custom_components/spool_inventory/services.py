"""Service schemas and the integration-level actions."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .manager import SpoolManager

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _color(value: Any) -> str:
    """Accept '#RRGGBB' or an [r, g, b] list; return '#rrggbb'."""
    if isinstance(value, str) and (match := _HEX_RE.match(value.strip())):
        return f"#{match.group(1).lower()}"
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            r, g, b = (int(v) for v in value)
        except (TypeError, ValueError) as err:
            raise vol.Invalid("color values must be integers") from err
        if all(0 <= v <= 255 for v in (r, g, b)):
            return f"#{r:02x}{g:02x}{b:02x}"
    raise vol.Invalid("color must be #RRGGBB or [r, g, b] with values 0-255")


_WEIGHT = vol.All(vol.Coerce(float), vol.Range(min=0, max=50000))
_WEIGHT_POSITIVE = vol.All(vol.Coerce(float), vol.Range(min=1, max=50000))
_DIAMETER = vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5))
_PRICE = vol.All(vol.Coerce(float), vol.Range(min=0))

# Descriptive fields shared by add_spool and update_spool.
_COMMON = {
    vol.Optional("product"): cv.string,
    vol.Optional("color_name"): cv.string,
    vol.Optional("color"): _color,
    vol.Optional("diameter"): _DIAMETER,
    vol.Optional("initial_weight"): _WEIGHT_POSITIVE,
    vol.Optional("spool_weight"): _WEIGHT,
    vol.Optional("price"): _PRICE,
    vol.Optional("location"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("tag_id"): cv.string,
    vol.Optional("loaded"): cv.boolean,
    vol.Optional("reorder"): cv.boolean,
    vol.Optional("refill"): cv.boolean,
}

ADD_SPOOL_SCHEMA = vol.Schema(
    {
        vol.Required("vendor"): vol.All(cv.string, vol.Length(min=1)),
        vol.Required("material"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("remaining_weight"): _WEIGHT,
        vol.Optional("gross_weight"): _WEIGHT,
        **_COMMON,
    }
)

# Entity services: the entity target is added by the platform.
UPDATE_SPOOL_SCHEMA = {
    vol.Optional("vendor"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("material"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("remaining_weight"): _WEIGHT,
    **_COMMON,
}
WEIGH_SPOOL_SCHEMA = {
    vol.Required("gross_weight"): _WEIGHT,
    vol.Optional("spool_weight"): _WEIGHT,
}
CONSUME_SCHEMA = {vol.Required("grams"): _WEIGHT}

LIST_SPOOLS_SCHEMA = vol.Schema(
    {
        vol.Optional("material"): cv.string,
        vol.Optional("vendor"): cv.string,
        vol.Optional("location"): cv.string,
        vol.Optional("loaded"): cv.boolean,
        vol.Optional("reorder"): cv.boolean,
    }
)


def _get_manager(hass: HomeAssistant) -> SpoolManager:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return entries[0].runtime_data


def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration-level actions (add_spool, list_spools)."""

    async def _add_spool(call: ServiceCall) -> ServiceResponse:
        spool = _get_manager(hass).async_add(dict(call.data))
        return {"spool_id": spool.id, "name": spool.display_name}

    async def _list_spools(call: ServiceCall) -> ServiceResponse:
        material = call.data.get("material", "").lower()
        vendor = call.data.get("vendor", "").lower()
        location = call.data.get("location", "").lower()
        loaded = call.data.get("loaded")
        reorder = call.data.get("reorder")
        return {
            "spools": [
                s.as_dict()
                for s in _get_manager(hass).active_spools
                if (not material or s.material.lower() == material)
                and (not vendor or s.vendor.lower() == vendor)
                and (not location or s.location.lower() == location)
                and (loaded is None or s.loaded == loaded)
                and (reorder is None or s.reorder == reorder)
            ]
        }

    hass.services.async_register(
        DOMAIN,
        "add_spool",
        _add_spool,
        schema=ADD_SPOOL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "list_spools",
        _list_spools,
        schema=LIST_SPOOLS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
