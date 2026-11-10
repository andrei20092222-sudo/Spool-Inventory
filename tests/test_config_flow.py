"""The 'Add integration' path: this is what the UI list and dialog use."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import async_get_custom_components, async_get_integration

from custom_components.spool_inventory.const import DOMAIN


async def test_integration_is_discoverable(hass: HomeAssistant) -> None:
    custom = await async_get_custom_components(hass)
    assert DOMAIN in custom
    integration = await async_get_integration(hass, DOMAIN)
    assert integration.config_flow is True
    assert integration.name == "Spool Inventory"
    assert integration.version is not None


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "0"


async def test_single_instance(hass: HomeAssistant) -> None:
    for _ in range(2):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        if result["type"] is FlowResultType.FORM:
            await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
