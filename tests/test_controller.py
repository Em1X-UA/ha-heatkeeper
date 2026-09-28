"""Behaviour tests for HeatKeeper modes, presence and one-shot heat."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.heatkeeper.const import CONF_GRID_ENTITY, CONF_ZONES, DOMAIN

from .conftest import ZONES


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.heatkeeper_mode", "option": option}, blocking=True,
    )
    await hass.async_block_till_done()


async def _number(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )
    await hass.async_block_till_done()


async def _switch(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    await hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entity_id: str) -> str:
    return hass.states.get(entity_id).state


def _targets(calls, kind: str) -> list[str]:
    return [c.data["entity_id"] for c in calls[kind]]


async def _at(hass: HomeAssistant, freezer: FrozenDateTimeFactory, hhmm: str) -> None:
    hour, minute = map(int, hhmm.split(":"))
    now = dt_util.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    freezer.move_to(target)
    async_fire_time_changed(hass, target)
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, **delta) -> None:
    freezer.tick(timedelta(**delta))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


ROOM_TARGET = "sensor.heatkeeper_room_zone_target"
KITCHEN_TARGET = "sensor.heatkeeper_kitchen_zone_target"


async def test_entities_and_grouped_names(hass, entry) -> None:
    """Targets live in rooms; presence switch only for rooms with an owner."""
    assert hass.states.get("number.heatkeeper_room_night_target") is not None
    assert hass.states.get("number.heatkeeper_night_target") is None
    assert hass.states.get("switch.heatkeeper_room_presence") is not None
    assert hass.states.get("switch.heatkeeper_kitchen_presence") is None
    assert hass.states.get("switch.heatkeeper_room_day_heating").state == "on"
    assert (
        hass.states.get("time.heatkeeper_cheap_start").attributes["friendly_name"]
        == "HeatKeeper Cheap tariff: start"
    )
    attrs = hass.states.get("sensor.heatkeeper_room_zone_status").attributes
    assert attrs["boost_entity"] == "switch.heatkeeper_room_boost"
    assert attrs["presence_entity"] == "switch.heatkeeper_room_presence"
    kitchen = hass.states.get("sensor.heatkeeper_kitchen_zone_status").attributes
    assert kitchen["presence_entity"] == "switch.heatkeeper_presence"


async def test_mode_off_does_nothing(hass, entry, calls) -> None:
    """Default mode is off and heaters are left alone."""
    assert _state(hass, "select.heatkeeper_mode") == "off"
    assert _state(hass, "sensor.heatkeeper_status") == "off"
    assert not calls["on"]


async def test_mode1_hysteresis_per_room(hass, entry, calls) -> None:
    """Each room keeps its own target with the shared delta."""
    await _number(hass, "number.heatkeeper_kitchen_maintain_target", 19)
    await _select(hass, "maintain")  # room 21 +-0.5, kitchen 19, temp 20
    assert _targets(calls, "on") == ["input_boolean.h1"]
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "sensor.t1", "21.2")  # inside band while on -> keep heating
    assert _targets(calls, "off") == []
    await _set(hass, "sensor.t1", "21.5")
    assert _targets(calls, "off") == ["input_boolean.h1"]
    assert _state(hass, ROOM_TARGET) == "21.0"
    assert _state(hass, KITCHEN_TARGET) == "19.0"


async def test_disable_zone(hass, entry, calls) -> None:
    """Disabling a room switches its heater off once."""
    await _select(hass, "maintain")
    await _set(hass, "input_boolean.h1", "on")
    await _switch(hass, "switch.heatkeeper_room_enabled", False)
    assert "input_boolean.h1" in _targets(calls, "off")
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "disabled"


async def test_mode2_schedule_and_presence(hass, entry, calls, freezer) -> None:
    """Night, pre-morning boost, and day targets from room / global presence."""
    await _select(hass, "tariff")
    await _at(hass, freezer, "02:00")
    assert _state(hass, "sensor.heatkeeper_status") == "night"
    assert _state(hass, "binary_sensor.heatkeeper_cheap_tariff") == "on"
    assert _state(hass, ROOM_TARGET) == "21.0"

    await _at(hass, freezer, "06:00")  # 60 min before 07:00, lead is 90
    assert _state(hass, "sensor.heatkeeper_status") == "preheat"
    assert _state(hass, ROOM_TARGET) == "23.0"

    await _at(hass, freezer, "12:00")
    assert _state(hass, "sensor.heatkeeper_status") == "day"
    assert _state(hass, ROOM_TARGET) == "21.0"

    # Room owner leaves: only the room drops to its away target.
    await _switch(hass, "switch.heatkeeper_room_presence", False)
    assert _state(hass, ROOM_TARGET) == "17.0"
    assert _state(hass, KITCHEN_TARGET) == "21.0"

    # Kitchen follows the global switch...
    await _switch(hass, "switch.heatkeeper_presence", False)
    assert _state(hass, KITCHEN_TARGET) == "17.0"
    # ...which in auto mode means "any owned room is home".
    await _switch(hass, "switch.heatkeeper_presence_auto", True)
    assert _state(hass, "switch.heatkeeper_presence") == "off"
    await _switch(hass, "switch.heatkeeper_room_presence", True)
    assert _state(hass, "switch.heatkeeper_presence") == "on"
    assert _state(hass, KITCHEN_TARGET) == "21.0"
    # Manual change turns auto off.
    await _switch(hass, "switch.heatkeeper_presence", False)
    assert _state(hass, "switch.heatkeeper_presence_auto") == "off"
    assert _state(hass, KITCHEN_TARGET) == "17.0"


async def test_day_heating_off_heats_only_at_night(hass, entry, calls, freezer) -> None:
    """With day heating off the room is not heated in the expensive zone."""
    await _switch(hass, "switch.heatkeeper_room_day_heating", False)
    await _at(hass, freezer, "12:00")
    await _select(hass, "tariff")
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "day_off"
    assert _targets(calls, "on") == ["input_boolean.h2"]
    await _at(hass, freezer, "02:00")
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "heating"
    assert "input_boolean.h1" in _targets(calls, "on")


async def test_mode2_tariff_entity(hass, entry, calls, freezer) -> None:
    """A tariff select with peak/offpeak decides the cheap zone."""
    options = dict(entry.options) | {"tariff_entity": "select.daily_energy"}
    hass.states.async_set("select.daily_energy", "peak")
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    await _select(hass, "tariff")
    await _at(hass, freezer, "02:00")
    assert _state(hass, "sensor.heatkeeper_status") == "day"
    await _set(hass, "select.daily_energy", "offpeak")
    assert _state(hass, "sensor.heatkeeper_status") == "night"


async def test_boost_switch_turns_itself_off(hass, entry, calls) -> None:
    """One-shot heat runs to the room's boost target, then the switch is off."""
    await _switch(hass, "switch.heatkeeper_room_boost", True)
    assert _targets(calls, "on") == ["input_boolean.h1"]
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "boost"
    assert _state(hass, "switch.heatkeeper_boost") == "on"
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "sensor.t1", "22.1")
    assert _targets(calls, "off") == ["input_boolean.h1"]
    assert _state(hass, "switch.heatkeeper_room_boost") == "off"
    assert _state(hass, "switch.heatkeeper_boost") == "off"
    await _set(hass, "input_boolean.h1", "off")
    await _set(hass, "sensor.t1", "19")
    assert _targets(calls, "on") == ["input_boolean.h1"]  # mode off: no re-heating


async def test_boost_all_and_cancel(hass, entry, calls) -> None:
    """The global switch starts and cancels every room."""
    await _switch(hass, "switch.heatkeeper_boost", True)
    assert set(_targets(calls, "on")) == {"input_boolean.h1", "input_boolean.h2"}
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "input_boolean.h2", "on")
    await _switch(hass, "switch.heatkeeper_boost", False)
    assert set(_targets(calls, "off")) == {"input_boolean.h1", "input_boolean.h2"}
    assert _state(hass, "switch.heatkeeper_room_boost") == "off"


async def test_boost_queued_without_power(hass, entry, calls, freezer) -> None:
    """Boost requested during an outage starts after power + delay."""
    await _tick(hass, freezer, minutes=5)  # leave startup grace
    await _set(hass, "binary_sensor.grid", "off")
    await _set(hass, "input_boolean.h1", "unavailable")
    await _switch(hass, "switch.heatkeeper_room_boost", True)
    assert _state(hass, "switch.heatkeeper_room_boost") == "on"
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "scheduled"

    await _set(hass, "binary_sensor.grid", "on")
    await _set(hass, "input_boolean.h1", "off")
    assert not calls["on"]
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "scheduled"
    await _tick(hass, freezer, minutes=5, seconds=1)
    assert _targets(calls, "on") == ["input_boolean.h1"]
    assert _state(hass, "sensor.heatkeeper_room_zone_status") == "boost"


async def test_active_boost_cancelled_by_outage(hass, entry, calls, freezer) -> None:
    """A running boost is cancelled when the power goes out."""
    await _tick(hass, freezer, minutes=5)
    await _switch(hass, "switch.heatkeeper_room_boost", True)
    await _set(hass, "binary_sensor.grid", "unavailable")
    assert _state(hass, "switch.heatkeeper_room_boost") == "off"


async def test_mode3_outage_and_auto_restore(hass, entry, calls, freezer) -> None:
    """Outage blocks heating, restore waits, then staggered recovery heat."""
    await _tick(hass, freezer, minutes=5)
    await _at(hass, freezer, "12:00")
    await _set(hass, "sensor.t1", "19.0")
    await _set(hass, "sensor.t2", "19.0")
    await _number(hass, "number.heatkeeper_kitchen_outage_target", 19.5)
    await _select(hass, "tariff_outage")
    assert _state(hass, "sensor.heatkeeper_status") == "day"
    calls["on"].clear()

    await _set(hass, "binary_sensor.grid", "unavailable")
    await _set(hass, "input_boolean.h1", "unavailable")
    await _set(hass, "input_boolean.h2", "unavailable")
    assert _state(hass, "sensor.heatkeeper_status") == "outage"
    assert _state(hass, "binary_sensor.heatkeeper_grid") == "off"

    # Power back: plugs come up "on" by themselves -> forced off, then wait.
    await _set(hass, "binary_sensor.grid", "on")
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "input_boolean.h2", "on")
    assert _state(hass, "sensor.heatkeeper_status") == "waiting"
    assert sorted(_targets(calls, "off")) == ["input_boolean.h1", "input_boolean.h2"]
    assert _state(hass, "sensor.heatkeeper_restore_at") not in ("unknown", None)
    await _set(hass, "input_boolean.h1", "off")
    await _set(hass, "input_boolean.h2", "off")
    assert not calls["on"]

    # After the 5 minute delay the first room starts, the second 30 s later.
    await _tick(hass, freezer, minutes=5, seconds=1)
    assert _state(hass, "sensor.heatkeeper_status") == "recovery"
    assert _targets(calls, "on") == ["input_boolean.h1"]
    assert _state(hass, ROOM_TARGET) == "20.0"
    await _tick(hass, freezer, seconds=31)
    assert _targets(calls, "on") == ["input_boolean.h1", "input_boolean.h2"]
    assert _state(hass, KITCHEN_TARGET) == "19.5"

    # Recovery targets reached -> back to normal day maintenance.
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "input_boolean.h2", "on")
    await _set(hass, "sensor.t1", "20.5")
    await _set(hass, "sensor.t2", "20.5")
    assert _state(hass, "sensor.heatkeeper_status") == "day"
    assert _state(hass, ROOM_TARGET) == "21.0"


async def test_mode3_manual_resume(hass, entry, calls, freezer) -> None:
    """Without auto restore heating stays paused until the resume button."""
    await _tick(hass, freezer, minutes=5)
    await _switch(hass, "switch.heatkeeper_auto_restore", False)
    await _number(hass, "number.heatkeeper_restore_delay", 0)
    await _select(hass, "tariff_outage")
    await _set(hass, "binary_sensor.grid", "off")
    await _set(hass, "binary_sensor.grid", "on")
    assert _state(hass, "sensor.heatkeeper_status") == "paused"
    calls["on"].clear()
    await _tick(hass, freezer, minutes=1)
    assert not calls["on"]

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.heatkeeper_resume"}, blocking=True
    )
    await hass.async_block_till_done()
    assert _state(hass, "sensor.heatkeeper_status") == "recovery"
    assert _targets(calls, "on") == ["input_boolean.h1"]


async def test_grid_ignored_for_heating_in_mode2(hass, entry, calls, freezer) -> None:
    """Regular heating only checks the grid in mode 3."""
    await _tick(hass, freezer, minutes=5)
    await _set(hass, "binary_sensor.grid", "off")
    await _select(hass, "maintain")
    assert set(_targets(calls, "on")) == {"input_boolean.h1", "input_boolean.h2"}


async def test_settings_persist(hass, entry, calls) -> None:
    """Settings survive a reload."""
    await _number(hass, "number.heatkeeper_room_night_target", 22.5)
    await _select(hass, "maintain")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "number.heatkeeper_room_night_target") == "22.5"
    assert _state(hass, "select.heatkeeper_mode") == "maintain"


async def test_migrates_v01_settings_and_entities(hass: HomeAssistant, hass_storage) -> None:
    """Global targets from 0.1 become room targets; old entities are removed."""
    config = MockConfigEntry(
        domain=DOMAIN,
        title="HeatKeeper",
        data={},
        options={CONF_ZONES: ZONES, CONF_GRID_ENTITY: "binary_sensor.grid"},
    )
    config.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{config.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{config.entry_id}",
        "data": {"settings": {"mode": "tariff", "night_target": 22.5}, "zones": {}},
    }
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "number", DOMAIN, f"{config.entry_id}_night_target", config_entry=config
    )
    registry.async_get_or_create(
        "button", DOMAIN, f"{config.entry_id}_z1_boost", config_entry=config
    )
    hass.states.async_set("sensor.t1", "20")
    hass.states.async_set("sensor.t2", "20")
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "number.heatkeeper_room_night_target") == "22.5"
    assert _state(hass, "number.heatkeeper_kitchen_night_target") == "22.5"
    assert registry.async_get_entity_id("number", DOMAIN, f"{config.entry_id}_night_target") is None
    assert registry.async_get_entity_id("button", DOMAIN, f"{config.entry_id}_z1_boost") is None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{config.entry_id}_z1_boost")
