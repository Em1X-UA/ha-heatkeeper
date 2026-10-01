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


# Newer HA links child devices by device id; `via_device` is deprecated there
# but older versions only understand `via_device`.
VIA_DEVICE_ID_SUPPORTED = "via_device_id" in DeviceInfo.__annotations__


def zone_device_info(controller: HeatKeeperController, zone: Zone) -> DeviceInfo:
    """Device for a single zone, linked to the main device."""
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{controller.entry.entry_id}_{zone.id}")},
        name=zone.name,
        manufacturer="HeatKeeper",
        model="Heating zone",
        suggested_area=zone.name,
        entry_type=DeviceEntryType.SERVICE,
    )
    if VIA_DEVICE_ID_SUPPORTED:
        if controller.main_device_id:
            info["via_device_id"] = controller.main_device_id  # type: ignore[typeddict-unknown-key]
    else:
        info["via_device"] = (DOMAIN, controller.entry.entry_id)  # type: ignore[typeddict-unknown-key]
    return info


class HeatKeeperEntity(Entity):
    """Entity backed by the controller; refreshed via dispatcher signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _platform_domain: str

    def __init__(
        self,
        controller: HeatKeeperController,
        key: str,
        zone: Zone | None = None,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the entity."""
        self._controller = controller
        self._zone = zone
        self._key = key
        self._attr_translation_key = translation_key or key
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
        controller.unique_ids.add((self._platform_domain, self._attr_unique_id))

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        if self._zone is not None:
            self._zone.entity_ids[f"{self._platform_domain}.{self._key}"] = (
                self.entity_id
            )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._controller.signal, self.async_write_ha_state
            )
        )
