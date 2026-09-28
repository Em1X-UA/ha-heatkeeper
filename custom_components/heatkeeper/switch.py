"""Switches for HeatKeeper."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import S_AUTO_RESTORE, Z_ENABLED
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    controller = entry.runtime_data
    entities: list[SwitchEntity] = [AutoRestoreSwitch(controller, S_AUTO_RESTORE)]
    entities.extend(
        ZoneEnabledSwitch(controller, Z_ENABLED, zone)
        for zone in controller.zones.values()
    )
    async_add_entities(entities)


class AutoRestoreSwitch(HeatKeeperEntity, SwitchEntity):
    """Resume heating automatically after a power outage."""

    _platform_domain = "switch"
    _attr_icon = "mdi:restart"

    @property
    def is_on(self) -> bool:
        """Return the setting."""
        return bool(self._controller.settings[S_AUTO_RESTORE])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto restore."""
        await self._controller.async_set_setting(S_AUTO_RESTORE, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto restore."""
        await self._controller.async_set_setting(S_AUTO_RESTORE, False)


class ZoneEnabledSwitch(HeatKeeperEntity, SwitchEntity):
    """Whether HeatKeeper controls this zone."""

    _platform_domain = "switch"
    _attr_icon = "mdi:radiator"

    @property
    def is_on(self) -> bool:
        """Return the setting."""
        return bool(self._controller.zone_settings[self._zone.id][Z_ENABLED])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the zone."""
        await self._controller.async_set_zone_setting(self._zone.id, Z_ENABLED, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the zone (heater is switched off once)."""
        await self._controller.async_set_zone_setting(self._zone.id, Z_ENABLED, False)
