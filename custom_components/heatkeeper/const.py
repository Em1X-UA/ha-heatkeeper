"""Constants for the HeatKeeper integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "heatkeeper"
VERSION: Final = "0.2.0"
STORAGE_VERSION: Final = 1

# Config entry options: external entities the controller reads.
CONF_TARIFF_ENTITY: Final = "tariff_entity"
CONF_TARIFF_CHEAP_STATES: Final = "tariff_cheap_states"
CONF_GRID_ENTITY: Final = "grid_entity"
CONF_GRID_ON_STATES: Final = "grid_on_states"
CONF_ZONES: Final = "zones"

# Zone definition keys.
CONF_ZONE_ID: Final = "id"
CONF_ZONE_NAME: Final = "name"
CONF_ZONE_HEATER: Final = "heater"
CONF_ZONE_TEMPERATURE: Final = "temperature"
CONF_ZONE_HUMIDITY: Final = "humidity"
CONF_ZONE_OWN_PRESENCE: Final = "own_presence"

DEFAULT_TARIFF_CHEAP_STATES: Final = "on, offpeak"
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
STATUS_DAY: Final = "day"
STATUS_OUTAGE: Final = "outage"
STATUS_WAITING: Final = "waiting"
STATUS_PAUSED: Final = "paused"
STATUS_RECOVERY: Final = "recovery"
STATUSES: Final = [
    STATUS_OFF,
    STATUS_MAINTAIN,
    STATUS_NIGHT,
    STATUS_PREHEAT,
    STATUS_DAY,
    STATUS_OUTAGE,
    STATUS_WAITING,
    STATUS_PAUSED,
    STATUS_RECOVERY,
]

# Per-zone status.
ZONE_HEATING: Final = "heating"
ZONE_IDLE: Final = "idle"
ZONE_BOOST: Final = "boost"
ZONE_SCHEDULED: Final = "scheduled"
ZONE_OFF: Final = "off"
ZONE_DAY_OFF: Final = "day_off"
ZONE_DISABLED: Final = "disabled"
ZONE_NO_SENSOR: Final = "no_sensor"
ZONE_BLOCKED: Final = "blocked"
ZONE_STATUSES: Final = [
    ZONE_HEATING,
    ZONE_IDLE,
    ZONE_BOOST,
    ZONE_SCHEDULED,
    ZONE_OFF,
    ZONE_DAY_OFF,
    ZONE_DISABLED,
    ZONE_NO_SENSOR,
    ZONE_BLOCKED,
]

# One-shot heat state of a zone.
BOOST_NONE: Final = None
BOOST_ACTIVE: Final = "active"
BOOST_QUEUED: Final = "queued"

# Grid state machine phases.
PHASE_NORMAL: Final = "normal"
PHASE_OUTAGE: Final = "outage"
PHASE_WAITING: Final = "waiting"
PHASE_PAUSED: Final = "paused"
PHASE_RECOVERY: Final = "recovery"

# Global settings (persisted in storage, exposed as entities).
S_MODE: Final = "mode"
S_DELTA: Final = "delta"
S_PREHEAT_LEAD: Final = "preheat_lead"
S_RESTORE_DELAY: Final = "restore_delay"
S_RESTORE_STAGGER: Final = "restore_stagger"
S_AUTO_RESTORE: Final = "auto_restore"
S_CHEAP_START: Final = "cheap_start"
S_CHEAP_END: Final = "cheap_end"
S_PRESENCE: Final = "presence"
S_PRESENCE_AUTO: Final = "presence_auto"

DEFAULT_SETTINGS: Final[dict] = {
    S_MODE: MODE_OFF,
    S_DELTA: 0.5,
    S_PREHEAT_LEAD: 90,
    S_RESTORE_DELAY: 5,
    S_RESTORE_STAGGER: 30,
    S_AUTO_RESTORE: True,
    S_CHEAP_START: "23:00:00",
    S_CHEAP_END: "07:00:00",
    S_PRESENCE: True,
    S_PRESENCE_AUTO: False,
}

# Per-zone settings.
Z_ENABLED: Final = "enabled"
Z_PRESENCE: Final = "presence"
Z_DAY_HEATING: Final = "day_heating"
T_MAINTAIN: Final = "maintain_target"
T_NIGHT: Final = "night_target"
T_PREHEAT: Final = "preheat_target"
T_DAY_HOME: Final = "day_home_target"
T_DAY_AWAY: Final = "day_away_target"
T_BOOST: Final = "boost_target"
T_OUTAGE: Final = "outage_target"
ZONE_TARGETS: Final = (
    T_MAINTAIN,
    T_NIGHT,
    T_PREHEAT,
    T_DAY_HOME,
    T_DAY_AWAY,
    T_BOOST,
    T_OUTAGE,
)

DEFAULT_ZONE_SETTINGS: Final[dict] = {
    Z_ENABLED: True,
    Z_PRESENCE: True,
    Z_DAY_HEATING: True,
    T_MAINTAIN: 21.0,
    T_NIGHT: 21.0,
    T_PREHEAT: 23.0,
    T_DAY_HOME: 21.0,
    T_DAY_AWAY: 17.0,
    T_BOOST: 22.0,
    T_OUTAGE: 20.0,
}

# How often the control loop re-evaluates even without state changes.
EVAL_INTERVAL_SECONDS: Final = 30
# Minimum time before re-sending the same command to a heater that ignored it.
COMMAND_RETRY_SECONDS: Final = 60
# Grace period after HA start during which an unavailable grid sensor is
# treated as "unknown" instead of "power outage".
STARTUP_GRACE_SECONDS: Final = 90

SIGNAL_UPDATE: Final = f"{DOMAIN}_update_{{}}"

CARD_URL: Final = f"/{DOMAIN}_static/heatkeeper-room-card.js"
