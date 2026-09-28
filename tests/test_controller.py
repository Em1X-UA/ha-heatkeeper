"""Behaviour tests for the three heating modes."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.heatkeeper_mode", "option": option}, blocking=True,
    )
    await hass.async_block_till_done()


async def _number(hass: HomeAssistant, key: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": f"number.heatkeeper_{key}", "value": value}, blocking=True,
    )
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


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


async def test_mode_off_does_nothing(hass, entry, calls) -> None:
    """Default mode is off and heaters are left alone."""
    assert hass.states.get("select.heatkeeper_mode").state == "off"
    assert hass.states.get("sensor.heatkeeper_status").state == "off"
    assert not calls["on"]


async def test_mode1_hysteresis(hass, entry, calls) -> None:
    """Turn on below target-delta, off above target+delta, hold in between."""
    await _select(hass, "maintain")  # target 21, delta 0.5, temp 20
    assert _targets(calls, "on") == ["input_boolean.h1", "input_boolean.h2"]
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "sensor.t1", "21.2")  # inside band while on -> keep heating
    assert _targets(calls, "off") == []
    await _set(hass, "sensor.t1", "21.5")
    assert _targets(calls, "off") == ["input_boolean.h1"]
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "21.0"


async def test_zone_offset_and_disable(hass, entry, calls) -> None:
    """Per-zone offset shifts the target; disabling a zone switches it off once."""
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.heatkeeper_kitchen_offset", "value": -2}, blocking=True,
    )
    await _select(hass, "maintain")
    assert _targets(calls, "on") == ["input_boolean.h1"]  # kitchen target 19 < 20
    await _set(hass, "input_boolean.h1", "on")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.heatkeeper_room_enabled"}, blocking=True
    )
    await hass.async_block_till_done()
    assert "input_boolean.h1" in _targets(calls, "off")
    assert hass.states.get("sensor.heatkeeper_room_zone_status").state == "disabled"


async def test_mode2_tariff_schedule(hass, entry, calls, freezer) -> None:
    """Night target, pre-morning boost, and day targets from the toggle."""
    await _select(hass, "tariff")
    await _at(hass, freezer, "02:00")
    assert hass.states.get("sensor.heatkeeper_status").state == "night"
    assert hass.states.get("binary_sensor.heatkeeper_cheap_tariff").state == "on"
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "21.0"

    await _at(hass, freezer, "06:00")  # 60 min before 07:00, lead is 90
    assert hass.states.get("sensor.heatkeeper_status").state == "preheat"
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "23.0"

    await _at(hass, freezer, "12:00")
    assert hass.states.get("sensor.heatkeeper_status").state == "day_home"
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "21.0"
    await _set(hass, "input_boolean.home", "off")
    assert hass.states.get("sensor.heatkeeper_status").state == "day_away"
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "17.0"


async def test_mode2_tariff_entity_overrides_times(hass, entry, calls, freezer) -> None:
    """A configured tariff entity decides the cheap zone."""
    options = dict(entry.options) | {"tariff_entity": "sensor.tariff", "tariff_cheap_states": "T2"}
    hass.states.async_set("sensor.tariff", "T1")
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    await _select(hass, "tariff")
    await _at(hass, freezer, "02:00")
    assert hass.states.get("sensor.heatkeeper_status").state == "day_home"
    await _set(hass, "sensor.tariff", "T2")
    assert hass.states.get("sensor.heatkeeper_status").state == "night"


async def test_one_shot_boost(hass, entry, calls) -> None:
    """Button heats to the boost target, then switches off and stays off."""
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.heatkeeper_room_boost"}, blocking=True
    )
    await hass.async_block_till_done()
    assert _targets(calls, "on") == ["input_boolean.h1"]
    assert hass.states.get("sensor.heatkeeper_room_zone_status").state == "boost"
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "sensor.t1", "22.1")
    assert _targets(calls, "off") == ["input_boolean.h1"]
    await _set(hass, "input_boolean.h1", "off")
    await _set(hass, "sensor.t1", "19")
    assert _targets(calls, "on") == ["input_boolean.h1"]  # mode off: no re-heating


async def test_mode3_outage_and_auto_restore(hass, entry, calls, freezer) -> None:
    """Outage blocks heating, restore waits, then staggered recovery heat."""
    freezer.tick(timedelta(minutes=5))  # leave startup grace
    await _at(hass, freezer, "12:00")
    await _set(hass, "sensor.t1", "19.0")
    await _set(hass, "sensor.t2", "19.0")
    await _select(hass, "tariff_outage")
    assert hass.states.get("sensor.heatkeeper_status").state == "day_home"
    calls["on"].clear()

    await _set(hass, "binary_sensor.grid", "unavailable")
    await _set(hass, "input_boolean.h1", "unavailable")
    await _set(hass, "input_boolean.h2", "unavailable")
    assert hass.states.get("sensor.heatkeeper_status").state == "outage"
    assert hass.states.get("binary_sensor.heatkeeper_grid").state == "off"

    # Power back: plugs come up "on" by themselves -> forced off, then wait.
    await _set(hass, "binary_sensor.grid", "on")
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "input_boolean.h2", "on")
    assert hass.states.get("sensor.heatkeeper_status").state == "waiting"
    assert sorted(_targets(calls, "off")) == ["input_boolean.h1", "input_boolean.h2"]
    assert hass.states.get("sensor.heatkeeper_restore_at").state not in ("unknown", None)
    await _set(hass, "input_boolean.h1", "off")
    await _set(hass, "input_boolean.h2", "off")
    assert not calls["on"]

    # After the 5 minute delay the first zone starts, the second 30 s later.
    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.heatkeeper_status").state == "recovery"
    assert _targets(calls, "on") == ["input_boolean.h1"]
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "20.0"
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _targets(calls, "on") == ["input_boolean.h1", "input_boolean.h2"]

    # Recovery target reached -> back to normal maintenance.
    await _set(hass, "input_boolean.h1", "on")
    await _set(hass, "input_boolean.h2", "on")
    await _set(hass, "sensor.t1", "20.5")
    await _set(hass, "sensor.t2", "20.5")
    assert hass.states.get("sensor.heatkeeper_status").state == "day_home"
    assert hass.states.get("sensor.heatkeeper_room_zone_target").state == "21.0"


async def test_mode3_manual_resume(hass, entry, calls, freezer) -> None:
    """Without auto restore heating stays paused until the resume button."""
    freezer.tick(timedelta(minutes=5))
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.heatkeeper_auto_restore"}, blocking=True
    )
    await _number(hass, "restore_delay", 0)
    await _select(hass, "tariff_outage")
    await _set(hass, "binary_sensor.grid", "off")
    await _set(hass, "binary_sensor.grid", "on")
    assert hass.states.get("sensor.heatkeeper_status").state == "paused"
    calls["on"].clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()
    assert not calls["on"]

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.heatkeeper_resume"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.heatkeeper_status").state == "recovery"
    assert _targets(calls, "on") == ["input_boolean.h1"]


async def test_mode3_ignores_grid_in_mode2(hass, entry, calls, freezer) -> None:
    """Grid sensor only matters in mode 3."""
    freezer.tick(timedelta(minutes=5))
    await _set(hass, "binary_sensor.grid", "off")
    await _select(hass, "tariff")
    assert set(_targets(calls, "on")) == {"input_boolean.h1", "input_boolean.h2"}


async def test_settings_persist(hass, entry, calls) -> None:
    """Settings survive a reload."""
    await _number(hass, "night_target", 22.5)
    await _select(hass, "maintain")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.heatkeeper_night_target").state == "22.5"
    assert hass.states.get("select.heatkeeper_mode").state == "maintain"
