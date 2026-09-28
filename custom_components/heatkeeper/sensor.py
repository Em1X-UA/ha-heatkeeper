"""Status sensors for HeatKeeper."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import STATUSES, ZONE_STATUSES
from .entity import HeatKeeperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    controller = entry.runtime_data
    entities: list[SensorEntity] = [
        StatusSensor(controller, "status"),
        RestoreAtSensor(controller, "restore_at"),
    ]
    for zone in controller.zones.values():
        entities.append(ZoneStatusSensor(controller, "zone_status", zone))
        entities.append(ZoneTargetSensor(controller, "zone_target", zone))
    async_add_entities(entities)


class StatusSensor(HeatKeeperEntity, SensorEntity):
    """What the system is doing right now."""

    _platform_domain = "sensor"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str:
        """Return the status."""
        return self._controller.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra details."""
        c = self._controller
        return {
            "cheap_tariff": c.cheap,
            "grid_ok": c.grid_ok,
            "phase": c.phase,
            "heating_zones": [
                z.name for z in c.zones.values() if z.status in ("heating", "boost")
            ],
        }


class RestoreAtSensor(HeatKeeperEntity, SensorEntity):
    """When heating resumes after the grid came back."""

    _platform_domain = "sensor"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-play-outline"

    @property
    def native_value(self) -> datetime | None:
        """Return the resume time."""
        return self._controller.restore_at


class ZoneStatusSensor(HeatKeeperEntity, SensorEntity):
    """Zone status."""

    _platform_domain = "sensor"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ZONE_STATUSES
    _attr_icon = "mdi:radiator"

    @property
    def native_value(self) -> str:
        """Return the zone status."""
        return self._zone.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details used by the HeatKeeper room card."""
        zone = self._zone
        ids = zone.entity_ids
        return {
            "zone_name": zone.name,
            "current_temperature": zone.current_temperature,
            "current_humidity": self._controller.read_float(zone.humidity_entity),
            "target_temperature": zone.target,
            "boost": zone.boost,
            "heater": zone.heater,
            "temperature_sensor": zone.temperature_entity,
            "humidity_sensor": zone.humidity_entity,
            "boost_entity": ids.get("switch.boost"),
            "presence_entity": ids.get("switch.presence")
            or self._controller.global_presence_entity,
            "day_heating_entity": ids.get("switch.day_heating"),
            "target_entity": ids.get("sensor.zone_target"),
        }


class ZoneTargetSensor(HeatKeeperEntity, SensorEntity):
    """Effective target temperature of a zone."""

    _platform_domain = "sensor"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the target."""
        return self._zone.target
