"""Switches for HeatKeeper."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import (
    S_AUTO_RESTORE,
    S_PRESENCE,
    S_PRESENCE_AUTO,
    Z_DAY_HEATING,
    Z_ENABLED,
    Z_PRESENCE,
)
from .controller import HeatKeeperController, Zone
from .entity import HeatKeeperEntity

BOOST = "boost"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    c = entry.runtime_data
    entities: list[SwitchEntity] = [
        GlobalPresenceSwitch(c, S_PRESENCE, translation_key="home_presence"),
        GlobalBoostSwitch(c, BOOST, translation_key="boost_all"),
        SettingSwitch(c, S_PRESENCE_AUTO, "mdi:account-multiple-check"),
        SettingSwitch(c, S_AUTO_RESTORE, "mdi:restart"),
    ]
    for zone in c.zones.values():
        entities.append(ZoneSettingSwitch(c, zone, Z_ENABLED, "mdi:radiator"))
        entities.append(ZoneSettingSwitch(c, zone, Z_DAY_HEATING, "mdi:weather-sunny"))
        if zone.own_presence:
            entities.append(ZoneSettingSwitch(c, zone, Z_PRESENCE, "mdi:account"))
        entities.append(ZoneBoostSwitch(c, BOOST, zone))
    async_add_entities(entities)


class SettingSwitch(HeatKeeperEntity, SwitchEntity):
    """A global boolean setting."""

    _platform_domain = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller: HeatKeeperController, key: str, icon: str) -> None:
        """Initialize."""
        super().__init__(controller, key)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        """Return the setting."""
        return bool(self._controller.settings[self._key])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable."""
        await self._controller.async_set_setting(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable."""
        await self._controller.async_set_setting(self._key, False)


class GlobalPresenceSwitch(HeatKeeperEntity, SwitchEntity):
    """'Someone home' for zones without an owner."""

    _platform_domain = "switch"
    _attr_icon = "mdi:home-account"

    async def async_added_to_hass(self) -> None:
        """Let zones without an owner point the card to this switch."""
        await super().async_added_to_hass()
        self._controller.global_presence_entity = self.entity_id

    @property
    def is_on(self) -> bool:
        """Return presence (computed when automatic)."""
        return self._controller.global_presence

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Someone is home (switches automatic mode off)."""
        await self._controller.async_set_global_presence(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Nobody is home (switches automatic mode off)."""
        await self._controller.async_set_global_presence(False)


class GlobalBoostSwitch(HeatKeeperEntity, SwitchEntity):
    """One-shot heat in every zone."""

    _platform_domain = "switch"
    _attr_icon = "mdi:fire"

    @property
    def is_on(self) -> bool:
        """On while any zone heats or waits for a one-shot heat."""
        return self._controller.boost_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start everywhere."""
        await self._controller.async_start_boost()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel everywhere."""
        await self._controller.async_cancel_boost()


class ZoneSettingSwitch(HeatKeeperEntity, SwitchEntity):
    """A per-zone boolean setting."""

    _platform_domain = "switch"

    def __init__(
        self, controller: HeatKeeperController, zone: Zone, key: str, icon: str
    ) -> None:
        """Initialize."""
        super().__init__(controller, key, zone)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        """Return the setting."""
        return bool(self._controller.zone_settings[self._zone.id][self._key])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable."""
        await self._controller.async_set_zone_setting(self._zone.id, self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable."""
        await self._controller.async_set_zone_setting(self._zone.id, self._key, False)


class ZoneBoostSwitch(HeatKeeperEntity, SwitchEntity):
    """One-shot heat in a single zone; turns itself off when done."""

    _platform_domain = "switch"
    _attr_icon = "mdi:fire"

    @property
    def is_on(self) -> bool:
        """On while heating or queued."""
        return self._zone.boost is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start."""
        await self._controller.async_start_boost(self._zone.id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel."""
        await self._controller.async_cancel_boost(self._zone.id)
