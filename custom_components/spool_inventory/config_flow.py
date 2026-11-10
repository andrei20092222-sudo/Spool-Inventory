"""Config flow for Spool Inventory (single instance, no options)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class SpoolInventoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the one-click setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry after a confirmation click."""
        if user_input is not None:
            return self.async_create_entry(title="Spool Inventory", data={})
        return self.async_show_form(step_id="user")
