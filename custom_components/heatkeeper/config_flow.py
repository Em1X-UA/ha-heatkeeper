"""Config and options flow for HeatKeeper."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .const import (
    CONF_DAY_TOGGLE_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_ON_STATES,
    CONF_TARIFF_CHEAP_STATES,
    CONF_TARIFF_ENTITY,
    CONF_ZONE_HEATER,
    CONF_ZONE_HUMIDITY,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONE_TEMPERATURE,
    CONF_ZONES,
    DEFAULT_GRID_ON_STATES,
    DEFAULT_TARIFF_CHEAP_STATES,
    DOMAIN,
)

CONF_ADD_ANOTHER = "add_another"
CONF_ZONE = "zone"
SOURCE_KEYS = (
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_CHEAP_STATES,
    CONF_GRID_ENTITY,
    CONF_GRID_ON_STATES,
    CONF_DAY_TOGGLE_ENTITY,
)
ZONE_KEYS = (CONF_ZONE_NAME, CONF_ZONE_HEATER, CONF_ZONE_TEMPERATURE, CONF_ZONE_HUMIDITY)


def _suggested(values: dict[str, Any], key: str) -> dict[str, Any]:
    return {"suggested_value": values.get(key)}


def _sources_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_TARIFF_ENTITY, description=_suggested(values, CONF_TARIFF_ENTITY)
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=["sensor", "binary_sensor", "input_boolean", "input_select", "select"]
                )
            ),
            vol.Optional(
                CONF_TARIFF_CHEAP_STATES,
                default=values.get(CONF_TARIFF_CHEAP_STATES, DEFAULT_TARIFF_CHEAP_STATES),
            ): TextSelector(),
            vol.Optional(
                CONF_GRID_ENTITY, description=_suggested(values, CONF_GRID_ENTITY)
            ): EntitySelector(
                EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
            ),
            vol.Optional(
                CONF_GRID_ON_STATES,
                default=values.get(CONF_GRID_ON_STATES, DEFAULT_GRID_ON_STATES),
            ): TextSelector(),
            vol.Optional(
                CONF_DAY_TOGGLE_ENTITY,
                description=_suggested(values, CONF_DAY_TOGGLE_ENTITY),
            ): EntitySelector(
                EntitySelectorConfig(domain=["input_boolean", "switch", "binary_sensor"])
            ),
        }
    )


def _zone_schema(values: dict[str, Any], add_another: bool) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_ZONE_NAME, description=_suggested(values, CONF_ZONE_NAME)
        ): TextSelector(),
        vol.Required(
            CONF_ZONE_HEATER, description=_suggested(values, CONF_ZONE_HEATER)
        ): EntitySelector(EntitySelectorConfig(domain=["switch", "input_boolean", "light"])),
        vol.Required(
            CONF_ZONE_TEMPERATURE, description=_suggested(values, CONF_ZONE_TEMPERATURE)
        ): EntitySelector(
            EntitySelectorConfig(domain=["sensor", "input_number"])
        ),
        vol.Optional(
            CONF_ZONE_HUMIDITY, description=_suggested(values, CONF_ZONE_HUMIDITY)
        ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="humidity")),
    }
    if add_another:
        schema[vol.Optional(CONF_ADD_ANOTHER, default=False)] = BooleanSelector()
    return vol.Schema(schema)


def _validate_zone(
    zone: dict[str, Any], zones: list[dict[str, Any]], zone_id: str | None = None
) -> dict[str, str]:
    errors: dict[str, str] = {}
    others = [z for z in zones if z[CONF_ZONE_ID] != zone_id]
    name = zone[CONF_ZONE_NAME].strip()
    if not name:
        errors[CONF_ZONE_NAME] = "name_required"
    elif any(z[CONF_ZONE_NAME].strip().lower() == name.lower() for z in others):
        errors[CONF_ZONE_NAME] = "name_exists"
    if any(z[CONF_ZONE_HEATER] == zone[CONF_ZONE_HEATER] for z in others):
        errors[CONF_ZONE_HEATER] = "heater_in_use"
    return errors


def _zone_from_input(user_input: dict[str, Any], zone_id: str) -> dict[str, Any]:
    zone = {key: user_input[key] for key in ZONE_KEYS if user_input.get(key)}
    zone[CONF_ZONE_NAME] = zone[CONF_ZONE_NAME].strip()
    zone[CONF_ZONE_ID] = zone_id
    return zone


def _apply_sources(options: dict[str, Any], user_input: dict[str, Any]) -> None:
    for key in SOURCE_KEYS:
        options.pop(key, None)
        if user_input.get(key):
            options[key] = user_input[key]


class HeatKeeperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: source entities, then zones."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._options: dict[str, Any] = {CONF_ZONES: []}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose tariff, grid and day toggle entities."""
        if user_input is not None:
            _apply_sources(self._options, user_input)
            return await self.async_step_zone()
        return self.async_show_form(step_id="user", data_schema=_sources_schema({}))

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a zone; repeat while 'add another' is ticked."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zone(user_input, self._options[CONF_ZONES])
            if not errors:
                self._options[CONF_ZONES].append(
                    _zone_from_input(user_input, uuid4().hex[:8])
                )
                if user_input.get(CONF_ADD_ANOTHER):
                    return self.async_show_form(
                        step_id="zone", data_schema=_zone_schema({}, True)
                    )
                return self.async_create_entry(
                    title="HeatKeeper", data={}, options=self._options
                )
        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(user_input or {}, True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HeatKeeperOptionsFlow()


class HeatKeeperOptionsFlow(OptionsFlow):
    """Edit source entities and zones."""

    def __init__(self) -> None:
        """Initialize."""
        self._options: dict[str, Any] | None = None
        self._zone_id: str | None = None

    @property
    def options(self) -> dict[str, Any]:
        """Working copy of the entry options."""
        if self._options is None:
            self._options = deepcopy(dict(self.config_entry.options))
            self._options.setdefault(CONF_ZONES, [])
        return self._options

    def _zone_choices(self) -> list[SelectOptionDict]:
        return [
            SelectOptionDict(value=z[CONF_ZONE_ID], label=z[CONF_ZONE_NAME])
            for z in self.options[CONF_ZONES]
        ]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Main menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["sources", "add_zone", "select_zone", "remove_zone"],
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit tariff, grid and day toggle entities."""
        if user_input is not None:
            _apply_sources(self.options, user_input)
            return self.async_create_entry(data=self.options)
        return self.async_show_form(
            step_id="sources", data_schema=_sources_schema(self.options)
        )

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new zone."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zone(user_input, self.options[CONF_ZONES])
            if not errors:
                self.options[CONF_ZONES].append(
                    _zone_from_input(user_input, uuid4().hex[:8])
                )
                return self.async_create_entry(data=self.options)
        return self.async_show_form(
            step_id="add_zone",
            data_schema=_zone_schema(user_input or {}, False),
            errors=errors,
        )

    async def async_step_select_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a zone to edit."""
        if not self.options[CONF_ZONES]:
            return self.async_abort(reason="no_zones")
        if user_input is not None:
            self._zone_id = user_input[CONF_ZONE]
            return await self.async_step_edit_zone()
        return self.async_show_form(
            step_id="select_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE): SelectSelector(
                        SelectSelectorConfig(options=self._zone_choices())
                    )
                }
            ),
        )

    async def async_step_edit_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected zone."""
        zones = self.options[CONF_ZONES]
        index = next(i for i, z in enumerate(zones) if z[CONF_ZONE_ID] == self._zone_id)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zone(user_input, zones, self._zone_id)
            if not errors:
                zones[index] = _zone_from_input(user_input, self._zone_id)
                return self.async_create_entry(data=self.options)
        return self.async_show_form(
            step_id="edit_zone",
            data_schema=_zone_schema(user_input or zones[index], False),
            errors=errors,
            description_placeholders={"zone": zones[index][CONF_ZONE_NAME]},
        )

    async def async_step_remove_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more zones."""
        if not self.options[CONF_ZONES]:
            return self.async_abort(reason="no_zones")
        if user_input is not None:
            remove = set(user_input.get(CONF_ZONES, []))
            self.options[CONF_ZONES] = [
                z for z in self.options[CONF_ZONES] if z[CONF_ZONE_ID] not in remove
            ]
            return self.async_create_entry(data=self.options)
        return self.async_show_form(
            step_id="remove_zone",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ZONES, default=[]): SelectSelector(
                        SelectSelectorConfig(options=self._zone_choices(), multiple=True)
                    )
                }
            ),
        )
