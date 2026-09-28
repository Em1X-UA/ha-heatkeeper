"""Cheap tariff window times for HeatKeeper."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import S_CHEAP_END, S_CHEAP_START
from .controller import parse_time
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up time entities."""
    controller = entry.runtime_data
    async_add_entities(
        [
            TariffTime(controller, S_CHEAP_START),
            TariffTime(controller, S_CHEAP_END),
        ]
    )


class TariffTime(HeatKeeperEntity, TimeEntity):
    """Start or end of the cheap tariff zone."""

    _platform_domain = "time"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> time:
        """Return the time."""
        return parse_time(self._controller.settings[self._key])

    async def async_set_value(self, value: time) -> None:
        """Store a new time."""
        await self._controller.async_set_setting(
            self._key, value.replace(microsecond=0).isoformat()
        )
