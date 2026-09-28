"""HeatKeeper: smart control of plug-switched electric heaters."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .controller import HeatKeeperController

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

type HeatKeeperConfigEntry = ConfigEntry[HeatKeeperController]


async def async_setup_entry(hass: HomeAssistant, entry: HeatKeeperConfigEntry) -> bool:
    """Set up HeatKeeper from a config entry."""
    controller = HeatKeeperController(hass, entry)
    await controller.async_load()
    entry.runtime_data = controller
    _remove_stale_zone_devices(hass, entry, controller)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeatKeeperConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete stored settings when the integration is removed."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after zones or source entities were changed."""
    await hass.config_entries.async_reload(entry.entry_id)


def _remove_stale_zone_devices(
    hass: HomeAssistant, entry: ConfigEntry, controller: HeatKeeperController
) -> None:
    """Remove devices of zones that were deleted in the options flow."""
    registry = dr.async_get(hass)
    valid = {(DOMAIN, entry.entry_id)} | {
        (DOMAIN, f"{entry.entry_id}_{zone_id}") for zone_id in controller.zones
    }
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & valid:
            registry.async_remove_device(device.id)
