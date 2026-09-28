"""Control logic for HeatKeeper.

The controller owns all editable settings (persisted in HA storage), reads the
external entities (temperature sensors, tariff, grid, day toggle) and switches
the heater plugs. Entities are thin views over the controller.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    callback,
    split_entity_id,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    COMMAND_RETRY_SECONDS,
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
    DEFAULT_SETTINGS,
    DEFAULT_TARIFF_CHEAP_STATES,
    DEFAULT_ZONE_SETTINGS,
    DOMAIN,
    EVAL_INTERVAL_SECONDS,
    MODE_MAINTAIN,
    MODE_OFF,
    MODE_TARIFF_OUTAGE,
    PHASE_NORMAL,
    PHASE_OUTAGE,
    PHASE_PAUSED,
    PHASE_RECOVERY,
    PHASE_WAITING,
    S_AUTO_RESTORE,
    S_BOOST_TARGET,
    S_CHEAP_END,
    S_CHEAP_START,
    S_DAY_AWAY_TARGET,
    S_DAY_HOME_TARGET,
    S_DELTA,
    S_MAINTAIN_TARGET,
    S_MODE,
    S_NIGHT_TARGET,
    S_OUTAGE_TARGET,
    S_PREHEAT_LEAD,
    S_PREHEAT_TARGET,
    S_RESTORE_DELAY,
    S_RESTORE_STAGGER,
    SIGNAL_UPDATE,
    STARTUP_GRACE_SECONDS,
    STATUS_DAY_AWAY,
    STATUS_DAY_HOME,
    STATUS_MAINTAIN,
    STATUS_NIGHT,
    STATUS_OFF,
    STATUS_OUTAGE,
    STATUS_PAUSED,
    STATUS_PREHEAT,
    STATUS_RECOVERY,
    STATUS_WAITING,
    STORAGE_VERSION,
    Z_ENABLED,
    Z_OFFSET,
    ZONE_BLOCKED,
    ZONE_BOOST,
    ZONE_DISABLED,
    ZONE_HEATING,
    ZONE_IDLE,
    ZONE_NO_SENSOR,
    ZONE_OFF,
)

_LOGGER = logging.getLogger(__name__)

_BAD_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN, None)


def parse_states(value: str | None, default: str) -> set[str]:
    """Parse a comma separated list of states into a lowercase set."""
    raw = value if value else default
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def parse_time(value: str | time) -> time:
    """Parse a stored HH:MM[:SS] string."""
    if isinstance(value, time):
        return value
    parsed = dt_util.parse_time(value)
    if parsed is None:
        raise ValueError(f"Invalid time: {value}")
    return parsed


def in_window(now: time, start: time, end: time) -> bool:
    """Return True if now is within [start, end), handling midnight wrap."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


@dataclass
class Zone:
    """Static config plus runtime state of one heating zone."""

    id: str
    name: str
    heater: str
    temperature_entity: str
    humidity_entity: str | None = None
    # Runtime state.
    boost: bool = False
    recovering: bool = False
    start_after: datetime | None = None
    force_off_once: bool = False
    target: float | None = None
    status: str = ZONE_IDLE
    current_temperature: float | None = None
    last_command: tuple[bool, datetime] | None = field(default=None, repr=False)

    @property
    def slug(self) -> str:
        """Slug used for entity ids."""
        return slugify(self.name) or self.id


class HeatKeeperController:
    """Central controller for all zones."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize from the config entry options."""
        self.hass = hass
        self.entry = entry
        opts = entry.options
        self.tariff_entity: str | None = opts.get(CONF_TARIFF_ENTITY)
        self.tariff_cheap_states = parse_states(
            opts.get(CONF_TARIFF_CHEAP_STATES), DEFAULT_TARIFF_CHEAP_STATES
        )
        self.grid_entity: str | None = opts.get(CONF_GRID_ENTITY)
        self.grid_on_states = parse_states(
            opts.get(CONF_GRID_ON_STATES), DEFAULT_GRID_ON_STATES
        )
        self.day_toggle_entity: str | None = opts.get(CONF_DAY_TOGGLE_ENTITY)
        self.zones: dict[str, Zone] = {
            z[CONF_ZONE_ID]: Zone(
                id=z[CONF_ZONE_ID],
                name=z[CONF_ZONE_NAME],
                heater=z[CONF_ZONE_HEATER],
                temperature_entity=z[CONF_ZONE_TEMPERATURE],
                humidity_entity=z.get(CONF_ZONE_HUMIDITY),
            )
            for z in opts.get(CONF_ZONES, [])
        }

        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.zone_settings: dict[str, dict[str, Any]] = {
            zid: dict(DEFAULT_ZONE_SETTINGS) for zid in self.zones
        }

        # Runtime state.
        self.status: str = STATUS_OFF
        self.phase: str = PHASE_NORMAL
        self.grid_ok: bool | None = None
        self.cheap: bool = False
        self.restored_at: datetime | None = None

        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._unsubs: list[CALLBACK_TYPE] = []
        self._wakeups: list[CALLBACK_TYPE] = []
        self._started_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._pending = False
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def signal(self) -> str:
        """Dispatcher signal for entity updates."""
        return SIGNAL_UPDATE.format(self.entry.entry_id)

    async def async_load(self) -> None:
        """Load persisted settings."""
        data = await self._store.async_load() or {}
        for key, value in (data.get("settings") or {}).items():
            if key in self.settings:
                self.settings[key] = value
        for zid, zdata in (data.get("zones") or {}).items():
            if zid in self.zone_settings:
                for key, value in zdata.items():
                    if key in self.zone_settings[zid]:
                        self.zone_settings[zid][key] = value
        if self.settings[S_MODE] == MODE_TARIFF_OUTAGE:
            self.phase = data.get("phase", PHASE_NORMAL)
            if restored := data.get("restored_at"):
                self.restored_at = dt_util.parse_datetime(restored)
            if self.phase == PHASE_RECOVERY:
                # Re-run the staggered start after a restart.
                self._begin_recovery(dt_util.utcnow())

    @callback
    def async_start(self) -> None:
        """Start listening to state changes and the evaluation timer."""
        watched = [
            eid
            for eid in (self.tariff_entity, self.grid_entity, self.day_toggle_entity)
            if eid
        ]
        for zone in self.zones.values():
            watched.extend([zone.heater, zone.temperature_entity])

        @callback
        def _state_changed(event: Event) -> None:
            self.async_request_evaluate()

        @callback
        def _interval(now: datetime) -> None:
            self.async_request_evaluate()

        @callback
        def _started(hass: HomeAssistant) -> None:
            self._started_at = dt_util.utcnow()
            self.async_request_evaluate()

        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, watched, _state_changed)
            )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, _interval, timedelta(seconds=EVAL_INTERVAL_SECONDS)
            )
        )
        self._unsubs.append(async_at_started(self.hass, _started))

    async def async_stop(self) -> None:
        """Stop all listeners."""
        self._stopped = True
        for unsub in self._unsubs + self._wakeups:
            unsub()
        self._unsubs.clear()
        self._wakeups.clear()
        # Flush pending changes so a reload does not lose them.
        await self._store.async_save(self._data_to_save())

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "settings": self.settings,
            "zones": self.zone_settings,
            "phase": self.phase,
            "restored_at": self.restored_at.isoformat() if self.restored_at else None,
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 1)

    # ------------------------------------------------------------------
    # Public API used by entities
    # ------------------------------------------------------------------

    @callback
    def async_request_evaluate(self) -> None:
        """Schedule an evaluation of all zones."""
        if not self._stopped:
            self.hass.async_create_task(self.async_evaluate())

    async def async_set_setting(self, key: str, value: Any) -> None:
        """Change a global setting."""
        old = self.settings.get(key)
        self.settings[key] = value
        if key == S_MODE and old != value:
            self._on_mode_changed(value)
        self._save()
        await self.async_evaluate()

    async def async_set_zone_setting(self, zone_id: str, key: str, value: Any) -> None:
        """Change a per-zone setting."""
        self.zone_settings[zone_id][key] = value
        if key == Z_ENABLED and not value:
            zone = self.zones[zone_id]
            zone.force_off_once = True
            zone.boost = False
        self._save()
        await self.async_evaluate()

    async def async_start_boost(self, zone_id: str | None = None) -> None:
        """One-shot heat to the boost target, then switch off."""
        for zone in self._select_zones(zone_id):
            if self.zone_settings[zone.id][Z_ENABLED]:
                zone.boost = True
        await self.async_evaluate()

    async def async_cancel_boost(self, zone_id: str | None = None) -> None:
        """Cancel a running one-shot heat."""
        for zone in self._select_zones(zone_id):
            if zone.boost:
                zone.boost = False
                zone.force_off_once = True
        await self.async_evaluate()

    async def async_resume(self) -> None:
        """Manually resume heating after a power outage."""
        if (
            self.settings[S_MODE] == MODE_TARIFF_OUTAGE
            and self.phase in (PHASE_WAITING, PHASE_PAUSED)
            and self.grid_ok
        ):
            self._begin_recovery(dt_util.utcnow())
            self._save()
        await self.async_evaluate()

    @property
    def restore_at(self) -> datetime | None:
        """When heating is allowed again after the grid came back."""
        if self.phase != PHASE_WAITING or self.restored_at is None:
            return None
        return self.restored_at + timedelta(minutes=self.settings[S_RESTORE_DELAY])

    def _select_zones(self, zone_id: str | None) -> list[Zone]:
        if zone_id is None:
            return list(self.zones.values())
        return [self.zones[zone_id]]

    def _on_mode_changed(self, mode: str) -> None:
        self._cancel_wakeups()
        self.phase = PHASE_NORMAL
        self.restored_at = None
        self.grid_ok = None
        for zone in self.zones.values():
            zone.recovering = False
            zone.start_after = None
            if mode == MODE_OFF:
                zone.force_off_once = True

    # ------------------------------------------------------------------
    # Reading external entities
    # ------------------------------------------------------------------

    def _state(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    def _read_float(self, entity_id: str | None) -> float | None:
        value = self._state(entity_id)
        if value in _BAD_STATES:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _in_startup_grace(self, now: datetime) -> bool:
        return self._started_at is None or now - self._started_at < timedelta(
            seconds=STARTUP_GRACE_SECONDS
        )

    def _read_grid(self, now: datetime) -> bool | None:
        """True = power present, False = outage, None = not known yet."""
        if not self.grid_entity:
            return True
        value = self._state(self.grid_entity)
        if value in _BAD_STATES:
            # The ESP sensor itself is powered from the grid, so it going
            # unavailable means an outage - unless HA just started.
            return None if self._in_startup_grace(now) else False
        return value.lower() in self.grid_on_states

    def _is_cheap(self, now_local: datetime) -> bool:
        if self.tariff_entity:
            value = self._state(self.tariff_entity)
            if value not in _BAD_STATES:
                return value.lower() in self.tariff_cheap_states
        return in_window(
            now_local.time(),
            parse_time(self.settings[S_CHEAP_START]),
            parse_time(self.settings[S_CHEAP_END]),
        )

    def _in_preheat(self, now_local: datetime) -> bool:
        lead = self.settings[S_PREHEAT_LEAD]
        if not lead:
            return False
        end = parse_time(self.settings[S_CHEAP_END])
        end_dt = now_local.replace(
            hour=end.hour, minute=end.minute, second=end.second, microsecond=0
        )
        if end_dt <= now_local:
            end_dt += timedelta(days=1)
        return end_dt - now_local <= timedelta(minutes=lead)

    def _is_home(self) -> bool:
        if not self.day_toggle_entity:
            return True
        value = self._state(self.day_toggle_entity)
        if value in _BAD_STATES:
            return True
        return value == STATE_ON

    # ------------------------------------------------------------------
    # Outage state machine (mode 3)
    # ------------------------------------------------------------------

    def _cancel_wakeups(self) -> None:
        for unsub in self._wakeups:
            unsub()
        self._wakeups.clear()

    def _schedule_wakeup(self, when: datetime) -> None:
        @callback
        def _wake(now: datetime) -> None:
            self.async_request_evaluate()

        self._wakeups.append(async_track_point_in_time(self.hass, _wake, when))

    def _begin_recovery(self, now: datetime) -> None:
        self._cancel_wakeups()
        self.phase = PHASE_RECOVERY
        self.restored_at = None
        stagger = timedelta(seconds=self.settings[S_RESTORE_STAGGER])
        heat_first = self.settings[S_OUTAGE_TARGET] > 0
        enabled = [z for z in self.zones.values() if self.zone_settings[z.id][Z_ENABLED]]
        for index, zone in enumerate(enabled):
            zone.start_after = now + stagger * index
            zone.recovering = heat_first
            if index:
                self._schedule_wakeup(zone.start_after)

    def _update_outage_phase(self, now: datetime) -> None:
        grid = self._read_grid(now)
        if grid is None:
            return
        self.grid_ok = grid
        if not grid:
            if self.phase != PHASE_OUTAGE:
                _LOGGER.info("Power outage detected, heating blocked")
                self._cancel_wakeups()
                self.phase = PHASE_OUTAGE
                self.restored_at = None
                for zone in self.zones.values():
                    zone.boost = False
                    zone.recovering = False
                    zone.start_after = None
                self._save()
            return

        if self.phase == PHASE_OUTAGE:
            _LOGGER.info("Power restored, waiting before heating")
            self.phase = PHASE_WAITING
            self.restored_at = now
            self._save()
        if self.phase == PHASE_WAITING:
            restore_at = self.restore_at
            if restore_at is None or now >= restore_at:
                if self.settings[S_AUTO_RESTORE]:
                    self._begin_recovery(now)
                else:
                    self.phase = PHASE_PAUSED
                    self.restored_at = None
                self._save()
            elif not self._wakeups:
                self._schedule_wakeup(restore_at)
        if self.phase == PHASE_RECOVERY:
            if all(
                not z.recovering and (z.start_after is None or now >= z.start_after)
                for z in self.zones.values()
            ):
                self.phase = PHASE_NORMAL
                for zone in self.zones.values():
                    zone.start_after = None
                self._save()

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def async_evaluate(self) -> None:
        """Evaluate all zones; coalesces concurrent requests."""
        if self._lock.locked():
            self._pending = True
            return
        async with self._lock:
            while True:
                self._pending = False
                await self._evaluate()
                if not self._pending or self._stopped:
                    break

    def _base_target(self, now_local: datetime) -> float:
        mode = self.settings[S_MODE]
        if mode == MODE_MAINTAIN:
            return self.settings[S_MAINTAIN_TARGET]
        if self.cheap:
            if self._in_preheat(now_local):
                return self.settings[S_PREHEAT_TARGET]
            return self.settings[S_NIGHT_TARGET]
        if self._is_home():
            return self.settings[S_DAY_HOME_TARGET]
        return self.settings[S_DAY_AWAY_TARGET]

    def _global_status(self, now_local: datetime) -> str:
        mode = self.settings[S_MODE]
        if mode == MODE_OFF:
            return STATUS_OFF
        if mode == MODE_MAINTAIN:
            return STATUS_MAINTAIN
        if mode == MODE_TARIFF_OUTAGE:
            phase_status = {
                PHASE_OUTAGE: STATUS_OUTAGE,
                PHASE_WAITING: STATUS_WAITING,
                PHASE_PAUSED: STATUS_PAUSED,
                PHASE_RECOVERY: STATUS_RECOVERY,
            }.get(self.phase)
            if phase_status:
                return phase_status
        if self.cheap:
            return STATUS_PREHEAT if self._in_preheat(now_local) else STATUS_NIGHT
        return STATUS_DAY_HOME if self._is_home() else STATUS_DAY_AWAY

    def _heater_on(self, zone: Zone) -> bool | None:
        value = self._state(zone.heater)
        if value in _BAD_STATES:
            return None
        return value == STATE_ON

    def _decide(self, zone: Zone, now: datetime, now_local: datetime) -> bool | None:
        """Return desired heater state (None = leave as is); sets zone status."""
        settings = self.settings
        zset = self.zone_settings[zone.id]
        mode = settings[S_MODE]
        offset = zset[Z_OFFSET]
        temp = self._read_float(zone.temperature_entity)
        zone.current_temperature = temp
        zone.target = None

        if not zset[Z_ENABLED]:
            zone.status = ZONE_DISABLED
            return False if zone.force_off_once else None

        outage_mode = mode == MODE_TARIFF_OUTAGE
        if outage_mode and (
            self.phase in (PHASE_OUTAGE, PHASE_WAITING)
            or (self.phase == PHASE_NORMAL and self.grid_ok is None and self.grid_entity)
            or (zone.start_after is not None and now < zone.start_after)
        ):
            zone.status = ZONE_BLOCKED
            return False

        if temp is None:
            # Never heat blind.
            zone.status = ZONE_NO_SENSOR
            return False

        if zone.boost:
            zone.target = settings[S_BOOST_TARGET] + offset
            if temp < zone.target:
                zone.status = ZONE_BOOST
                return True
            # Reached: switch off and hand control back to the normal logic.
            zone.boost = False
            zone.status = ZONE_IDLE
            return False

        if mode == MODE_OFF:
            zone.status = ZONE_OFF
            return False if zone.force_off_once else None

        if outage_mode and self.phase == PHASE_PAUSED:
            zone.status = ZONE_BLOCKED
            return False

        if zone.recovering:
            zone.target = settings[S_OUTAGE_TARGET] + offset
            if temp < zone.target:
                zone.status = ZONE_HEATING
                return True
            zone.recovering = False

        target = self._base_target(now_local) + offset
        zone.target = target
        delta = settings[S_DELTA]
        is_on = self._heater_on(zone)
        if temp <= target - delta:
            desired: bool | None = True
        elif temp >= target + delta:
            desired = False
        else:
            desired = is_on
        zone.status = ZONE_HEATING if desired else ZONE_IDLE
        return desired

    async def _apply(self, zone: Zone, desired: bool | None, now: datetime) -> None:
        if desired is None:
            return
        is_on = self._heater_on(zone)
        if is_on is None:
            return
        if is_on == desired:
            zone.last_command = None
            return
        if (
            zone.last_command is not None
            and zone.last_command[0] == desired
            and now - zone.last_command[1] < timedelta(seconds=COMMAND_RETRY_SECONDS)
        ):
            return
        zone.last_command = (desired, now)
        domain = split_entity_id(zone.heater)[0]
        _LOGGER.debug("%s: turning heater %s", zone.name, "on" if desired else "off")
        await self.hass.services.async_call(
            domain,
            SERVICE_TURN_ON if desired else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: zone.heater},
            blocking=False,
        )

    async def _evaluate(self) -> None:
        now = dt_util.utcnow()
        now_local = dt_util.now()
        self.cheap = self._is_cheap(now_local)
        if self.settings[S_MODE] == MODE_TARIFF_OUTAGE:
            self._update_outage_phase(now)
        else:
            self.grid_ok = self._read_grid(now)

        for zone in self.zones.values():
            desired = self._decide(zone, now, now_local)
            try:
                await self._apply(zone, desired, now)
            except Exception:  # noqa: BLE001 - keep controlling other zones
                _LOGGER.exception("Failed to switch heater %s", zone.heater)
            zone.force_off_once = False

        if self.settings[S_MODE] == MODE_TARIFF_OUTAGE:
            # Recovery may have finished in this pass.
            self._update_outage_phase(now)
        self.status = self._global_status(now_local)
        async_dispatcher_send(self.hass, self.signal)

