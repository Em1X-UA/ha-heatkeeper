"""Constants for the HeatKeeper integration."""

from __future__ import annotations

from datetime import time
from typing import Final

DOMAIN: Final = "heatkeeper"
STORAGE_VERSION: Final = 1

# Config entry options: external entities the controller reads.
CONF_TARIFF_ENTITY: Final = "tariff_entity"
CONF_TARIFF_CHEAP_STATES: Final = "tariff_cheap_states"
CONF_GRID_ENTITY: Final = "grid_entity"
CONF_GRID_ON_STATES: Final = "grid_on_states"
CONF_DAY_TOGGLE_ENTITY: Final = "day_toggle_entity"
CONF_ZONES: Final = "zones"

# Zone definition keys.
CONF_ZONE_ID: Final = "id"
CONF_ZONE_NAME: Final = "name"
CONF_ZONE_HEATER: Final = "heater"
CONF_ZONE_TEMPERATURE: Final = "temperature"
CONF_ZONE_HUMIDITY: Final = "humidity"

DEFAULT_TARIFF_CHEAP_STATES: Final = "on"
DEFAULT_GRID_ON_STATES: Final = "on"

# Operating modes.
MODE_OFF: Final = "off"
MODE_MAINTAIN: Final = "maintain"
MODE_TARIFF: Final = "tariff"
MODE_TARIFF_OUTAGE: Final = "tariff_outage"
MODES: Final = [MODE_OFF, MODE_MAINTAIN, MODE_TARIFF, MODE_TARIFF_OUTAGE]

# Global status reported by the status sensor.
STATUS_OFF: Final = "off"
STATUS_MAINTAIN: Final = "maintain"
STATUS_NIGHT: Final = "night"
STATUS_PREHEAT: Final = "preheat"
STATUS_DAY_HOME: Final = "day_home"
STATUS_DAY_AWAY: Final = "day_away"
STATUS_OUTAGE: Final = "outage"
STATUS_WAITING: Final = "waiting"
STATUS_PAUSED: Final = "paused"
STATUS_RECOVERY: Final = "recovery"
STATUSES: Final = [
    STATUS_OFF,
    STATUS_MAINTAIN,
    STATUS_NIGHT,
    STATUS_PREHEAT,
    STATUS_DAY_HOME,
    STATUS_DAY_AWAY,
    STATUS_OUTAGE,
    STATUS_WAITING,
    STATUS_PAUSED,
    STATUS_RECOVERY,
]

# Per-zone status.
ZONE_HEATING: Final = "heating"
ZONE_IDLE: Final = "idle"
ZONE_BOOST: Final = "boost"
ZONE_OFF: Final = "off"
ZONE_DISABLED: Final = "disabled"
ZONE_NO_SENSOR: Final = "no_sensor"
ZONE_BLOCKED: Final = "blocked"
ZONE_STATUSES: Final = [
    ZONE_HEATING,
    ZONE_IDLE,
    ZONE_BOOST,
    ZONE_OFF,
    ZONE_DISABLED,
    ZONE_NO_SENSOR,
    ZONE_BLOCKED,
]

# Outage state machine phases (mode 3 only).
PHASE_NORMAL: Final = "normal"
PHASE_OUTAGE: Final = "outage"
PHASE_WAITING: Final = "waiting"
PHASE_PAUSED: Final = "paused"
PHASE_RECOVERY: Final = "recovery"

# Editable settings (persisted in storage, exposed as entities).
S_MODE: Final = "mode"
S_MAINTAIN_TARGET: Final = "maintain_target"
S_DELTA: Final = "delta"
S_NIGHT_TARGET: Final = "night_target"
S_PREHEAT_TARGET: Final = "preheat_target"
S_PREHEAT_LEAD: Final = "preheat_lead"
S_DAY_HOME_TARGET: Final = "day_home_target"
S_DAY_AWAY_TARGET: Final = "day_away_target"
S_BOOST_TARGET: Final = "boost_target"
S_OUTAGE_TARGET: Final = "outage_target"
S_RESTORE_DELAY: Final = "restore_delay"
S_RESTORE_STAGGER: Final = "restore_stagger"
S_AUTO_RESTORE: Final = "auto_restore"
S_CHEAP_START: Final = "cheap_start"
S_CHEAP_END: Final = "cheap_end"

DEFAULT_SETTINGS: Final[dict] = {
    S_MODE: MODE_OFF,
    S_MAINTAIN_TARGET: 21.0,
    S_DELTA: 0.5,
    S_NIGHT_TARGET: 21.0,
    S_PREHEAT_TARGET: 23.0,
    S_PREHEAT_LEAD: 90,
    S_DAY_HOME_TARGET: 21.0,
    S_DAY_AWAY_TARGET: 17.0,
    S_BOOST_TARGET: 22.0,
    S_OUTAGE_TARGET: 20.0,
    S_RESTORE_DELAY: 5,
    S_RESTORE_STAGGER: 30,
    S_AUTO_RESTORE: True,
    S_CHEAP_START: "23:00:00",
    S_CHEAP_END: "07:00:00",
}

# Per-zone editable settings.
Z_ENABLED: Final = "enabled"
Z_OFFSET: Final = "offset"
DEFAULT_ZONE_SETTINGS: Final[dict] = {Z_ENABLED: True, Z_OFFSET: 0.0}

DEFAULT_CHEAP_START: Final = time(23, 0)
DEFAULT_CHEAP_END: Final = time(7, 0)

# How often the control loop re-evaluates even without state changes.
EVAL_INTERVAL_SECONDS: Final = 30
# Minimum time before re-sending the same command to a heater that ignored it.
COMMAND_RETRY_SECONDS: Final = 60
# Grace period after HA start during which an unavailable grid sensor is
# treated as "unknown" instead of "power outage".
STARTUP_GRACE_SECONDS: Final = 90

SIGNAL_UPDATE: Final = f"{DOMAIN}_update_{{}}"
