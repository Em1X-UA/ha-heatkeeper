"""Editable numeric parameters for HeatKeeper."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeatKeeperConfigEntry
from .const import (
    S_DELTA,
    S_PREHEAT_LEAD,
    S_RESTORE_DELAY,
    S_RESTORE_STAGGER,
    T_BOOST,
    T_DAY_AWAY,
    T_DAY_HOME,
    T_MAINTAIN,
    T_NIGHT,
    T_OUTAGE,
    T_PREHEAT,
)
from .controller import HeatKeeperController, Zone
from .entity import HeatKeeperEntity


@dataclass(frozen=True, kw_only=True)
class HKNumberDescription(NumberEntityDescription):
    """Number description with defaults for temperature targets."""

    native_min_value: float = 5
    native_max_value: float = 30
    native_step: float = 0.5
    native_unit_of_measurement: str | None = UnitOfTemperature.CELSIUS
    device_class: NumberDeviceClass | None = NumberDeviceClass.TEMPERATURE
    mode: NumberMode = NumberMode.BOX
    entity_category: EntityCategory | None = EntityCategory.CONFIG


GLOBAL_NUMBERS: tuple[HKNumberDescription, ...] = (
    HKNumberDescription(
        key=S_DELTA,
        icon="mdi:plus-minus-variant",
        native_min_value=0.1,
        native_max_value=3,
        native_step=0.1,
        device_class=None,
    ),
    HKNumberDescription(
        key=S_PREHEAT_LEAD,
        icon="mdi:timer-sand",
        native_min_value=0,
        native_max_value=360,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=None,
    ),
    HKNumberDescription(
        key=S_RESTORE_DELAY,
        icon="mdi:timer-outline",
        native_min_value=0,
        native_max_value=120,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=None,
    ),
    HKNumberDescription(
        key=S_RESTORE_STAGGER,
        icon="mdi:stairs",
        native_min_value=0,
        native_max_value=600,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=None,
    ),
)

ZONE_NUMBERS: tuple[HKNumberDescription, ...] = (
    HKNumberDescription(key=T_MAINTAIN, icon="mdi:thermometer"),
    HKNumberDescription(key=T_NIGHT, icon="mdi:weather-night"),
    HKNumberDescription(key=T_PREHEAT, icon="mdi:thermometer-chevron-up"),
    HKNumberDescription(key=T_DAY_HOME, icon="mdi:home-thermometer"),
    HKNumberDescription(key=T_DAY_AWAY, icon="mdi:home-export-outline"),
    HKNumberDescription(key=T_BOOST, icon="mdi:fire"),
    HKNumberDescription(key=T_OUTAGE, icon="mdi:transmission-tower", native_min_value=0),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatKeeperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    controller = entry.runtime_data
    entities: list[NumberEntity] = [
        GlobalNumber(controller, desc) for desc in GLOBAL_NUMBERS
    ]
    for zone in controller.zones.values():
        entities.extend(ZoneNumber(controller, desc, zone) for desc in ZONE_NUMBERS)
    async_add_entities(entities)


class GlobalNumber(HeatKeeperEntity, NumberEntity):
    """A global numeric setting."""

    _platform_domain = "number"

    def __init__(
        self, controller: HeatKeeperController, description: HKNumberDescription
    ) -> None:
        """Initialize."""
        self.entity_description = description
        super().__init__(controller, description.key)

    @property
    def native_value(self) -> float:
        """Current value."""
        return self._controller.settings[self._key]

    async def async_set_native_value(self, value: float) -> None:
        """Store a new value."""
        if self.native_step >= 1:
            value = int(value)
        await self._controller.async_set_setting(self._key, value)


class ZoneNumber(HeatKeeperEntity, NumberEntity):
    """A per-zone target temperature."""

    _platform_domain = "number"

    def __init__(
        self,
        controller: HeatKeeperController,
        description: HKNumberDescription,
        zone: Zone,
    ) -> None:
        """Initialize."""
        self.entity_description = description
        super().__init__(controller, description.key, zone)

    @property
    def native_value(self) -> float:
        """Current value."""
        return self._controller.zone_settings[self._zone.id][self._key]

    async def async_set_native_value(self, value: float) -> None:
        """Store a new value."""
        await self._controller.async_set_zone_setting(self._zone.id, self._key, value)
