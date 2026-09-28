"""Buttons for HeatKeeper."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([ResumeButton(entry.runtime_data, "resume")])


class ResumeButton(HeatKeeperEntity, ButtonEntity):
    """Resume heating after a power outage without waiting."""

    _platform_domain = "button"
    _attr_icon = "mdi:play-circle-outline"

    async def async_press(self) -> None:
        """Resume heating."""
        await self._controller.async_resume()
