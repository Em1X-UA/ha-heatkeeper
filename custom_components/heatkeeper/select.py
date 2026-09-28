"""Mode selector for HeatKeeper."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import MODES, S_MODE
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the mode select."""
    async_add_entities([ModeSelect(entry.runtime_data, S_MODE)])


class ModeSelect(HeatKeeperEntity, SelectEntity):
    """Operating mode."""

    _platform_domain = "select"
    _attr_options = MODES
    _attr_icon = "mdi:radiator"

    @property
    def current_option(self) -> str:
        """Return the active mode."""
        return self._controller.settings[S_MODE]

    async def async_select_option(self, option: str) -> None:
        """Change the mode."""
        await self._controller.async_set_setting(S_MODE, option)
