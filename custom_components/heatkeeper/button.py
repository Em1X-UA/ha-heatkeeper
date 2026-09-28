"""Buttons for HeatKeeper."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .entity import HeatKeeperEntity

BOOST = "boost"
BOOST_CANCEL = "boost_cancel"
RESUME = "resume"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    controller = entry.runtime_data
    entities: list[ButtonEntity] = [
        HeatKeeperButton(controller, BOOST),
        HeatKeeperButton(controller, BOOST_CANCEL),
        HeatKeeperButton(controller, RESUME),
    ]
    entities.extend(
        HeatKeeperButton(controller, BOOST, zone) for zone in controller.zones.values()
    )
    async_add_entities(entities)


class HeatKeeperButton(HeatKeeperEntity, ButtonEntity):
    """Action button."""

    _platform_domain = "button"

    async def async_press(self) -> None:
        """Run the action."""
        zone_id = self._zone.id if self._zone else None
        if self._key == BOOST:
            await self._controller.async_start_boost(zone_id)
        elif self._key == BOOST_CANCEL:
            await self._controller.async_cancel_boost(zone_id)
        elif self._key == RESUME:
            await self._controller.async_resume()
