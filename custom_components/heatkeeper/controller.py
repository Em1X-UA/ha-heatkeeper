"""Control logic for HeatKeeper.

The controller owns all editable settings (persisted in HA storage), reads the
external entities (temperature sensors, tariff, grid) and switches the heater
plugs. Entities are thin views over the controller.
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
    BOOST_ACTIVE,
    BOOST_QUEUED,
    COMMAND_RETRY_SECONDS,
    CONF_GRID_ENTITY,
    CONF_GRID_ON_STATES,
    CONF_TARIFF_CHEAP_STATES,
    CONF_TARIFF_ENTITY,
    CONF_ZONE_HEATER,
    CONF_ZONE_HUMIDITY,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONE_OWN_PRESENCE,
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
    S_CHEAP_END,
    S_CHEAP_START,
    S_DELTA,
    S_MODE,
    S_PREHEAT_LEAD,
    S_PRESENCE,
    S_PRESENCE_AUTO,
    S_RESTORE_DELAY,
    S_RESTORE_STAGGER,
    SIGNAL_UPDATE,
    STARTUP_GRACE_SECONDS,
    STATUS_DAY,
    STATUS_MAINTAIN,
    STATUS_NIGHT,
    STATUS_OFF,
    STATUS_OUTAGE,
    STATUS_PAUSED,
    STATUS_PREHEAT,
    STATUS_RECOVERY,
    STATUS_WAITING,
    STORAGE_VERSION,
    T_BOOST,
    T_DAY_AWAY,
    T_DAY_HOME,
    T_MAINTAIN,
    T_NIGHT,
    T_OUTAGE,
    T_PREHEAT,
    Z_DAY_HEATING,
    Z_ENABLED,
    Z_PRESENCE,
    ZONE_BLOCKED,
    ZONE_BOOST,
    ZONE_DAY_OFF,
    ZONE_DISABLED,
    ZONE_HEATING,
    ZONE_IDLE,
    ZONE_NO_SENSOR,
    ZONE_OFF,
    ZONE_SCHEDULED,
    ZONE_TARGETS,
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
    own_presence: bool = True
    # Runtime state.
    boost: str | None = None
    recovering: bool = False
    start_after: datetime | None = None
    force_off_once: bool = False
    target: float | None = None
    status: str = ZONE_IDLE
    current_temperature: float | None = None
    last_command: tuple[bool, datetime] | None = field(default=None, repr=False)
    # Entity ids of this zone's entities, keyed by entity key (for the card).
    entity_ids: dict[str, str] = field(default_factory=dict, repr=False)

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
        self.zones: dict[str, Zone] = {
            z[CONF_ZONE_ID]: Zone(
                id=z[CONF_ZONE_ID],
                name=z[CONF_ZONE_NAME],
                heater=z[CONF_ZONE_HEATER],
                temperature_entity=z[CONF_ZONE_TEMPERATURE],
                humidity_entity=z.get(CONF_ZONE_HUMIDITY),
                own_presence=z.get(CONF_ZONE_OWN_PRESENCE, True),
            )
            for z in opts.get(CONF_ZONES, [])
        }

        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.zone_settings: dict[str, dict[str, Any]] = {
            zid: dict(DEFAULT_ZONE_SETTINGS) for zid in self.zones
        }
        # (platform domain, unique id) of every entity created this setup.
        self.unique_ids: set[tuple[str, str]] = set()
        # Entity id of the global presence switch (set when it is added).
        self.global_presence_entity: str | None = None
        # Device registry id of the main HeatKeeper device (set on setup).
        self.main_device_id: str | None = None

        # Runtime state.
        self.status: str = STATUS_OFF
        self.phase: str = PHASE_NORMAL
        self.grid_ok: bool | None = None if self.grid_entity else True
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
        """Load persisted settings (and migrate global targets to zones)."""
        data = await self._store.async_load() or {}
        stored_settings = data.get("settings") or {}
        for key, value in stored_settings.items():
            if key in self.settings:
                self.settings[key] = value
        stored_zones = data.get("zones") or {}
        for zid, zset in self.zone_settings.items():
            # Version 0.1 kept targets globally: use them as zone defaults.
            for key in ZONE_TARGETS:
                if key in stored_settings:
                    zset[key] = stored_settings[key]
            for key, value in (stored_zones.get(zid) or {}).items():
                if key in zset:
                    zset[key] = value
        for zid, state in (data.get("boost") or {}).items():
            if zid in self.zones and state in (BOOST_ACTIVE, BOOST_QUEUED):
                self.zones[zid].boost = state
        if self.grid_entity:
            self.phase = data.get("phase", PHASE_NORMAL)
            if restored := data.get("restored_at"):
                self.restored_at = dt_util.parse_datetime(restored)
            if self.phase == PHASE_RECOVERY:
                if self.settings[S_MODE] == MODE_TARIFF_OUTAGE:
                    self._begin_recovery(dt_util.utcnow())
                else:
                    self.phase = PHASE_NORMAL

    @callback
    def async_start(self) -> None:
        """Start listening to state changes and the evaluation timer."""
        watched = [eid for eid in (self.tariff_entity, self.grid_entity) if eid]
        for zone in self.zones.values():
            watched.extend([zone.heater, zone.temperature_entity])
            if zone.humidity_entity:
                watched.append(zone.humidity_entity)

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
        """Stop all listeners and flush settings."""
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
            "boost": {z.id: z.boost for z in self.zones.values() if z.boost},
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

    async def async_set_global_presence(self, value: bool) -> None:
        """Manually set 'someone home'; this switches automatic mode off."""
        self.settings[S_PRESENCE] = value
        self.settings[S_PRESENCE_AUTO] = False
        self._save()
        await self.async_evaluate()

    async def async_set_zone_setting(self, zone_id: str, key: str, value: Any) -> None:
        """Change a per-zone setting."""
        self.zone_settings[zone_id][key] = value
        if key == Z_ENABLED and not value:
            zone = self.zones[zone_id]
            zone.force_off_once = True
            zone.boost = None
        self._save()
        await self.async_evaluate()

    async def async_start_boost(self, zone_id: str | None = None) -> None:
        """One-shot heat to the zone's boost target, then switch off.

        Without power the request is queued and starts after the grid is back
        and the restore delay has passed.
        """
        state = BOOST_ACTIVE if self._power_available() else BOOST_QUEUED
        for zone in self._select_zones(zone_id):
            if self.zone_settings[zone.id][Z_ENABLED] and not zone.boost:
                zone.boost = state
        self._save()
        await self.async_evaluate()

    async def async_cancel_boost(self, zone_id: str | None = None) -> None:
        """Cancel a running or queued one-shot heat."""
        for zone in self._select_zones(zone_id):
            if zone.boost:
                zone.boost = None
                zone.force_off_once = True
        self._save()
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
    def boost_on(self) -> bool:
        """True while any zone runs or waits for a one-shot heat."""
        return any(zone.boost for zone in self.zones.values())

    @property
    def global_presence(self) -> bool:
        """'Someone home': manual, or any owned room when automatic."""
        if self.settings[S_PRESENCE_AUTO]:
            owned = [z for z in self.zones.values() if z.own_presence]
            if owned:
                return any(self.zone_settings[z.id][Z_PRESENCE] for z in owned)
        return bool(self.settings[S_PRESENCE])

    def zone_home(self, zone: Zone) -> bool:
        """Presence that applies to a zone."""
        if zone.own_presence:
            return bool(self.zone_settings[zone.id][Z_PRESENCE])
        return self.global_presence

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
        # Recovery and pause only exist in mode 3.
        if self.phase in (PHASE_RECOVERY, PHASE_PAUSED):
            self.phase = PHASE_NORMAL
        for zone in self.zones.values():
            zone.recovering = False
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

    def read_float(self, entity_id: str | None) -> float | None:
        """Read a numeric state, None when unavailable."""
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
            # A grid-powered sensor going unavailable means an outage -
            # unless HA just started and it has not connected yet.
            return None if self._in_startup_grace(now) else False
        return value.lower() in self.grid_on_states

    def _power_available(self) -> bool:
        if not self.grid_entity:
            return True
        return self.grid_ok is True and self.phase not in (PHASE_OUTAGE, PHASE_WAITING)

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

    # ------------------------------------------------------------------
    # Grid state machine
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

    def _stagger(self, now: datetime, zones: list[Zone]) -> None:
        """Give zones start times spaced by the stagger interval."""
        step = timedelta(seconds=self.settings[S_RESTORE_STAGGER])
        for index, zone in enumerate(zones):
            zone.start_after = now + step * index
            if index:
                self._schedule_wakeup(zone.start_after)

    def _begin_recovery(self, now: datetime) -> None:
        """Mode 3: start zones one by one, each first heating to its outage target."""
        self._cancel_wakeups()
        self.phase = PHASE_RECOVERY
        self.restored_at = None
        enabled = [
            z for z in self.zones.values() if self.zone_settings[z.id][Z_ENABLED]
        ]
        for zone in enabled:
            zone.recovering = self.zone_settings[zone.id][T_OUTAGE] > 0
        self._stagger(now, enabled)

    def _finish_waiting(self, now: datetime) -> None:
        self._cancel_wakeups()
        self.restored_at = None
        queued = [z for z in self.zones.values() if z.boost == BOOST_QUEUED]
        if self.settings[S_MODE] == MODE_TARIFF_OUTAGE:
            if self.settings[S_AUTO_RESTORE]:
                self._begin_recovery(now)
                return
            self.phase = PHASE_PAUSED
        else:
            self.phase = PHASE_RECOVERY if queued else PHASE_NORMAL
        self._stagger(now, queued)

    def _update_grid(self, now: datetime) -> None:
        grid = self._read_grid(now)
        if grid is None:
            return
        self.grid_ok = grid
        if not self.grid_entity:
            return
        if not grid:
            if self.phase != PHASE_OUTAGE:
                _LOGGER.info("Power outage detected")
                self._cancel_wakeups()
                self.phase = PHASE_OUTAGE
                self.restored_at = None
                for zone in self.zones.values():
                    if zone.boost == BOOST_ACTIVE:
                        zone.boost = None
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
                self._finish_waiting(now)
                self._save()
            elif not self._wakeups:
                self._schedule_wakeup(restore_at)

        if self.phase not in (PHASE_OUTAGE, PHASE_WAITING):
            for zone in self.zones.values():
                if zone.boost == BOOST_QUEUED:
                    zone.boost = BOOST_ACTIVE
                if zone.start_after is not None and now >= zone.start_after:
                    zone.start_after = None
        if self.phase == PHASE_RECOVERY and all(
            not z.recovering and z.start_after is None for z in self.zones.values()
        ):
            self.phase = PHASE_NORMAL
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

    def _base_target(self, zone: Zone, now_local: datetime) -> float | None:
        """Target of the current mode; None = do not heat (day heating off)."""
        zset = self.zone_settings[zone.id]
        if self.settings[S_MODE] == MODE_MAINTAIN:
            return zset[T_MAINTAIN]
        if self.cheap:
            if self._in_preheat(now_local):
                return zset[T_PREHEAT]
            return zset[T_NIGHT]
        if not zset[Z_DAY_HEATING]:
            return None
        return zset[T_DAY_HOME] if self.zone_home(zone) else zset[T_DAY_AWAY]

    def _global_status(self, now_local: datetime) -> str:
        mode = self.settings[S_MODE]
        if mode == MODE_OFF:
            return STATUS_OFF
        if mode == MODE_TARIFF_OUTAGE:
            phase_status = {
                PHASE_OUTAGE: STATUS_OUTAGE,
                PHASE_WAITING: STATUS_WAITING,
                PHASE_PAUSED: STATUS_PAUSED,
                PHASE_RECOVERY: STATUS_RECOVERY,
            }.get(self.phase)
            if phase_status:
                return phase_status
        if mode == MODE_MAINTAIN:
            return STATUS_MAINTAIN
        if self.cheap:
            return STATUS_PREHEAT if self._in_preheat(now_local) else STATUS_NIGHT
        return STATUS_DAY

    def _heater_on(self, zone: Zone) -> bool | None:
        value = self._state(zone.heater)
        if value in _BAD_STATES:
            return None
        return value == STATE_ON

    def _decide(self, zone: Zone, now: datetime, now_local: datetime) -> bool | None:
        """Return desired heater state (None = leave as is); sets zone status."""
        zset = self.zone_settings[zone.id]
        mode = self.settings[S_MODE]
        temp = self.read_float(zone.temperature_entity)
        zone.current_temperature = temp
        zone.target = None

        if not zset[Z_ENABLED]:
            zone.status = ZONE_DISABLED
            return False if zone.force_off_once else None

        waiting_power = bool(self.grid_entity) and (
            self.grid_ok is None or self.phase in (PHASE_OUTAGE, PHASE_WAITING)
        )
        staggered = zone.start_after is not None and now < zone.start_after
        if mode == MODE_TARIFF_OUTAGE and (waiting_power or staggered):
            zone.status = ZONE_SCHEDULED if zone.boost else ZONE_BLOCKED
            return False

        if temp is None:
            # Never heat blind.
            zone.status = ZONE_NO_SENSOR
            return False

        if zone.boost == BOOST_ACTIVE and not staggered:
            zone.target = zset[T_BOOST]
            if temp < zone.target:
                zone.status = ZONE_BOOST
                return True
            # Reached: switch off and hand control back to the normal logic.
            zone.boost = None
            self._save()
            zone.status = ZONE_IDLE
            return False

        desired = self._decide_mode(zone, temp, now_local)
        if zone.boost and not desired:
            zone.status = ZONE_SCHEDULED
        return desired

    def _decide_mode(self, zone: Zone, temp: float, now_local: datetime) -> bool | None:
        zset = self.zone_settings[zone.id]
        mode = self.settings[S_MODE]
        if mode == MODE_OFF:
            zone.status = ZONE_OFF
            return False if zone.force_off_once else None

        if mode == MODE_TARIFF_OUTAGE and self.phase == PHASE_PAUSED:
            zone.status = ZONE_BLOCKED
            return False

        if zone.recovering:
            zone.target = zset[T_OUTAGE]
            if temp < zone.target:
                zone.status = ZONE_HEATING
                return True
            zone.recovering = False

        target = self._base_target(zone, now_local)
        if target is None:
            zone.status = ZONE_DAY_OFF
            return False
        zone.target = target
        delta = self.settings[S_DELTA]
        if temp <= target - delta:
            desired: bool | None = True
        elif temp >= target + delta:
            desired = False
        else:
            desired = self._heater_on(zone)
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
        self._update_grid(now)

        for zone in self.zones.values():
            desired = self._decide(zone, now, now_local)
            try:
                await self._apply(zone, desired, now)
            except Exception:  # noqa: BLE001 - keep controlling other zones
                _LOGGER.exception("Failed to switch heater %s", zone.heater)
            zone.force_off_once = False

        # Recovery may have finished in this pass.
        self._update_grid(now)
        self.status = self._global_status(now_local)
        async_dispatcher_send(self.hass, self.signal)
