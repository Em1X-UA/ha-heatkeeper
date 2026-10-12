"""HeatKeeper: smart control of plug-switched electric heaters."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, DOMAIN, STORAGE_VERSION, VERSION
from .controller import HeatKeeperController
from .entity import main_device_info

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

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)
CARD_FILE = Path(__file__).parent / "frontend" / "heatkeeper-room-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the room card and make every dashboard load it."""
    if hass.http is None:  # e.g. in tests without the HTTP server
        return True
    from homeassistant.components.http import StaticPathConfig

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )

    async def _register(_: HomeAssistant | None = None) -> None:
        if not await _async_register_card_resource(hass):
            _add_card_extra_js(hass)

    # Lovelace is fully set up only once HA has started.
    async_at_started(hass, _register)
    return True


def _add_card_extra_js(hass: HomeAssistant) -> None:
    """Fallback: inject the card script into every page (not awaited by dashboards)."""
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")


async def _async_register_card_resource(hass: HomeAssistant) -> bool:
    """Register the card as a Lovelace module resource.

    Dashboards wait for resources before rendering, so the card always exists
    when a view is built. A script added with add_extra_js_url is not awaited:
    on a slow connection (a phone) the view can be built first and show
    "Custom element doesn't exist". Returns False when resources cannot be
    managed (YAML mode), so the caller can fall back to extra JS.
    """
    url = f"{CARD_URL}?v={VERSION}"
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None or not hasattr(resources, "async_create_item"):
            return False
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        for item in resources.async_items():
            if str(item["url"]).split("?")[0] != CARD_URL:
                continue
            if item["url"] != url:
                await resources.async_update_item(
                    item["id"], {"res_type": "module", "url": url}
                )
            return True
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001 - never break setup over a dashboard resource
        _LOGGER.debug("Could not register the room card resource", exc_info=True)
        return False
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HeatKeeperConfigEntry) -> bool:
    """Set up HeatKeeper from a config entry."""
    controller = HeatKeeperController(hass, entry)
    await controller.async_load()
    entry.runtime_data = controller
    # Register the main device first so room devices can link to its id.
    controller.main_device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id, **main_device_info(controller)
        )
        .id
    )
    _remove_stale_zone_devices(hass, entry, controller)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _remove_stale_entities(hass, entry, controller)
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


def _remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, controller: HeatKeeperController
) -> None:
    """Remove entities from older versions (e.g. global targets, old buttons)."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (entity.domain, entity.unique_id) not in controller.unique_ids:
            registry.async_remove(entity.entity_id)
