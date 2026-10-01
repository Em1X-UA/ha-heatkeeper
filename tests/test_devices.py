"""Device registry linking tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.heatkeeper import entity as hk_entity
from custom_components.heatkeeper.const import DOMAIN


async def test_room_devices_linked_to_main_device(hass: HomeAssistant, entry) -> None:
    """Room devices hang below the main HeatKeeper device."""
    registry = dr.async_get(hass)
    main = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    room = registry.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}_z1")})
    assert main is not None and room is not None
    assert room.via_device_id == main.id
    assert entry.runtime_data.main_device_id == main.id


async def test_new_ha_uses_via_device_id(hass: HomeAssistant, entry, monkeypatch) -> None:
    """On HA versions with `via_device_id` the deprecated `via_device` is not used."""
    controller = entry.runtime_data
    zone = controller.zones["z1"]
    monkeypatch.setattr(hk_entity, "VIA_DEVICE_ID_SUPPORTED", True)
    info = hk_entity.zone_device_info(controller, zone)
    assert info["via_device_id"] == controller.main_device_id
    assert "via_device" not in info
    monkeypatch.setattr(hk_entity, "VIA_DEVICE_ID_SUPPORTED", False)
    info = hk_entity.zone_device_info(controller, zone)
    assert info["via_device"] == (DOMAIN, entry.entry_id)
    assert "via_device_id" not in info


def test_version_matches_manifest() -> None:
    """The card cache-buster version must match the released manifest version."""
    import json
    from pathlib import Path

    from custom_components.heatkeeper.const import VERSION

    manifest = Path(__file__).parents[1] / "custom_components/heatkeeper/manifest.json"
    assert json.loads(manifest.read_text())["version"] == VERSION
