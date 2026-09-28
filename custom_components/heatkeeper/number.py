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
    S_BOOST_TARGET,
    S_DAY_AWAY_TARGET,
    S_DAY_HOME_TARGET,
    S_DELTA,
    S_MAINTAIN_TARGET,
    S_NIGHT_TARGET,
    S_OUTAGE_TARGET,
    S_PREHEAT_LEAD,
    S_PREHEAT_TARGET,
    S_RESTORE_DELAY,
    S_RESTORE_STAGGER,
    Z_OFFSET,
)
from .controller import HeatKeeperController, Zone
from .entity import HeatKeeperEntity


@dataclass(frozen=True, kw_only=True)
class HKNumberDescription(NumberEntityDescription):
    """Number description with sane defaults for temperatures."""

    native_min_value: float = 5
    native_max_value: float = 30
    native_step: float = 0.5
    native_unit_of_measurement: str | None = UnitOfTemperature.CELSIUS
    device_class: NumberDeviceClass | None = NumberDeviceClass.TEMPERATURE
    mode: NumberMode = NumberMode.BOX


GLOBAL_NUMBERS: tuple[HKNumberDescription, ...] = (
    HKNumberDescription(key=S_MAINTAIN_TARGET, icon="mdi:thermometer"),
    HKNumberDescription(
        key=S_DELTA,
        icon="mdi:plus-minus-variant",
        native_min_value=0.1,
        native_max_value=3,
        native_step=0.1,
        device_class=None,
    ),
    HKNumberDescription(key=S_NIGHT_TARGET, icon="mdi:weather-night"),
    HKNumberDescription(key=S_PREHEAT_TARGET, icon="mdi:thermometer-chevron-up"),
    HKNumberDescription(
        key=S_PREHEAT_LEAD,
        icon="mdi:timer-sand",
        native_min_value=0,
        native_max_value=360,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=None,
    ),
    HKNumberDescription(key=S_DAY_HOME_TARGET, icon="mdi:home-thermometer"),
    HKNumberDescription(key=S_DAY_AWAY_TARGET, icon="mdi:home-export-outline"),
    HKNumberDescription(key=S_BOOST_TARGET, icon="mdi:fire"),
    HKNumberDescription(
        key=S_OUTAGE_TARGET, icon="mdi:transmission-tower", native_min_value=0
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

ZONE_OFFSET = HKNumberDescription(
    key=Z_OFFSET,
    icon="mdi:thermometer-plus",
    native_min_value=-5,
    native_max_value=5,
    native_step=0.5,
    device_class=None,
    entity_category=EntityCategory.CONFIG,
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
    entities.extend(
        ZoneNumber(controller, ZONE_OFFSET, zone) for zone in controller.zones.values()
    )
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
    """A per-zone numeric setting."""

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
