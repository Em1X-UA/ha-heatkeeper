"""Base entity for HeatKeeper."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import HeatKeeperController, Zone


def main_device_info(controller: HeatKeeperController) -> DeviceInfo:
    """Device that groups the global controls."""
    return DeviceInfo(
        identifiers={(DOMAIN, controller.entry.entry_id)},
        name="HeatKeeper",
        manufacturer="HeatKeeper",
        model="Heating controller",
        entry_type=DeviceEntryType.SERVICE,
    )


def zone_device_info(controller: HeatKeeperController, zone: Zone) -> DeviceInfo:
    """Device for a single zone, linked to the main device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{controller.entry.entry_id}_{zone.id}")},
        name=zone.name,
        manufacturer="HeatKeeper",
        model="Heating zone",
        suggested_area=zone.name,
        via_device=(DOMAIN, controller.entry.entry_id),
        entry_type=DeviceEntryType.SERVICE,
    )


class HeatKeeperEntity(Entity):
    """Entity backed by the controller; refreshed via dispatcher signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _platform_domain: str

    def __init__(
        self, controller: HeatKeeperController, key: str, zone: Zone | None = None
    ) -> None:
        """Initialize the entity."""
        self._controller = controller
        self._zone = zone
        self._key = key
        self._attr_translation_key = key
        entry_id = controller.entry.entry_id
        if zone is None:
            self._attr_unique_id = f"{entry_id}_{key}"
            self._attr_device_info = main_device_info(controller)
            object_id = f"heatkeeper_{key}"
        else:
            self._attr_unique_id = f"{entry_id}_{zone.id}_{key}"
            self._attr_device_info = zone_device_info(controller, zone)
            object_id = f"heatkeeper_{zone.slug}_{key}"
        # Stable, language-independent entity ids so dashboards are portable.
        self.entity_id = f"{self._platform_domain}.{object_id}"

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._controller.signal, self.async_write_ha_state
            )
        )
