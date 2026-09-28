"""Config and options flow tests."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.heatkeeper.const import CONF_ZONES, DOMAIN


async def test_user_flow_creates_zones(hass: HomeAssistant) -> None:
    """Sources step, then two zones."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tariff_cheap_states": "on", "grid_on_states": "on"}
    )
    assert result["step_id"] == "zone"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Кухня", "heater": "switch.h1", "temperature": "sensor.t1", "add_another": True},
    )
    assert result["step_id"] == "zone"
    # Same heater again is rejected.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Спальня", "heater": "switch.h1", "temperature": "sensor.t2"},
    )
    assert result["errors"] == {"heater": "heater_in_use"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Спальня", "heater": "switch.h2", "temperature": "sensor.t2"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    zones = result["options"][CONF_ZONES]
    assert [z["name"] for z in zones] == ["Кухня", "Спальня"]
    await hass.async_block_till_done()
    assert hass.states.get("select.heatkeeper_mode") is not None
    assert hass.states.get("sensor.heatkeeper_kukhnia_zone_target") is not None


async def test_options_add_and_remove_zone(hass: HomeAssistant, entry) -> None:
    """Zones can be added and removed from the options flow."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_zone"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Bedroom", "heater": "switch.h3", "temperature": "sensor.t3", "own_presence": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.options[CONF_ZONES]) == 3
    assert hass.states.get("switch.heatkeeper_bedroom_enabled") is not None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_zone"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"zones": ["z1"]}
    )
    await hass.async_block_till_done()
    assert [z["id"] for z in entry.options[CONF_ZONES]][0] == "z2"
    assert hass.states.get("switch.heatkeeper_room_enabled") is None
