"""Binary sensors for HeatKeeper."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    controller = entry.runtime_data
    entities: list[BinarySensorEntity] = [CheapTariffSensor(controller, "cheap_tariff")]
    if controller.grid_entity:
        entities.append(GridSensor(controller, "grid"))
    async_add_entities(entities)


class CheapTariffSensor(HeatKeeperEntity, BinarySensorEntity):
    """On while the cheap (night) tariff is active."""

    _platform_domain = "binary_sensor"
    _attr_icon = "mdi:cash-clock"

    @property
    def is_on(self) -> bool:
        """Return True in the cheap zone."""
        return self._controller.cheap


class GridSensor(HeatKeeperEntity, BinarySensorEntity):
    """Grid power as seen by HeatKeeper."""

    _platform_domain = "binary_sensor"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool | None:
        """Return True when power is present."""
        return self._controller.grid_ok
