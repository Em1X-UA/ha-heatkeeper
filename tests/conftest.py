"""Fixtures for HeatKeeper tests."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.heatkeeper.const import (
    CONF_GRID_ENTITY,
    CONF_ZONE_HEATER,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONE_OWN_PRESENCE,
    CONF_ZONE_TEMPERATURE,
    CONF_ZONES,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    return


ZONES = [
    {
        CONF_ZONE_ID: "z1",
        CONF_ZONE_NAME: "Room",
        CONF_ZONE_HEATER: "input_boolean.h1",
        CONF_ZONE_TEMPERATURE: "sensor.t1",
        CONF_ZONE_OWN_PRESENCE: True,
    },
    {
        CONF_ZONE_ID: "z2",
        CONF_ZONE_NAME: "Kitchen",
        CONF_ZONE_HEATER: "input_boolean.h2",
        CONF_ZONE_TEMPERATURE: "sensor.t2",
        CONF_ZONE_OWN_PRESENCE: False,
    },
]


@pytest.fixture
def calls(hass: HomeAssistant, entry):
    """Record heater commands (registered after the switch platform loads)."""
    on = async_mock_service(hass, "input_boolean", "turn_on")
    off = async_mock_service(hass, "input_boolean", "turn_off")
    return {"on": on, "off": off}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A configured HeatKeeper entry with two zones."""
    hass.states.async_set("input_boolean.h1", "off")
    hass.states.async_set("input_boolean.h2", "off")
    hass.states.async_set("sensor.t1", "20.0")
    hass.states.async_set("sensor.t2", "20.0")
    hass.states.async_set("binary_sensor.grid", "on")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="HeatKeeper",
        data={},
        options={
            CONF_ZONES: ZONES,
            CONF_GRID_ENTITY: "binary_sensor.grid",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
