# HeatKeeper for Home Assistant

**English** · [Українська](README.uk.md)

![HeatKeeper](docs/banner.jpg)

Smart control of electric heaters switched by smart plugs (on/off).
Each room has one plug and one temperature sensor. The integration handles a two-zone
(day/night) tariff, per-room presence and power outages. Everything is configured in the UI.

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → `https://github.com/Em1X-UA/ha-heatkeeper`, type **Integration**.
2. Find **HeatKeeper** in HACS, install it and restart Home Assistant.
3. **Settings → Devices & services → Add integration → HeatKeeper**.

## Configuration

**Sources** (all optional; change them later via **HeatKeeper → Configure**):

| Field | Purpose |
|---|---|
| Tariff entity | Current tariff zone, e.g. `select.daily_energy` with states `peak`/`offpeak`. List the "cheap" states comma separated (default `on, offpeak`). If empty, the cheap zone comes from the "Cheap tariff: start/end" times. |
| Grid presence entity | Any entity that is on while there is power (a sensor, a plug, …). `unavailable` also counts as "no power". |

**Rooms.** For every room set a name, a heater plug, a temperature sensor, an optional humidity sensor and
the **"Room has an owner"** checkbox. A room with an owner gets its own presence switch. A room without an owner
(kitchen, living room) follows the shared "Presence: someone home" switch.

## Modes

| Mode | Behaviour |
|---|---|
| **Off** | Switching to this mode turns all heaters off; after that they are left alone. One-shot heat still works. |
| **Maintain temperature** | Heating turns on at `t ≤ target − delta` and off at `t ≥ target + delta`. |
| **Two-zone tariff** | Cheap zone: *night target*. Shortly before the cheap zone ends: *pre-morning boost*. Expensive zone: day target *home* or *away* depending on presence. With **Day heating** off, a room is heated only at night. |
| **Tariff + outages** | Same, plus power-outage protection (see below). |

Every target is set **per room**. The hysteresis (±) is shared.

> The pre-morning boost is counted from "Cheap tariff: end", even when the tariff comes from an entity.
> Set it to the time your tariff switches to `peak`.

### Presence

- **A room with an owner** has its own "Presence" switch. Drive it with anything: a phone,
  a button, an automation.
- **"Presence: someone home"** is the shared switch for rooms without an owner.
- **"Presence: auto (any room)"**, when on, makes the shared switch follow "any owner is home".
  Changing the shared switch by hand turns auto off.
- Presence has no effect at night.

### Power outages ("Tariff + outages" mode)

1. Power is gone → status **Power outage**, heating is blocked.
2. Power is back → all plugs are switched **off** right away, because smart plugs often turn
   themselves on after power returns. Then the **delay after power returns** runs.
3. After the delay:
   - **auto restore on** → rooms start one by one, spaced by *stagger between rooms*.
     Each room first heats to its *after-outage target* (`0` = skip), then returns to normal maintenance;
   - **auto restore off** → **paused** until you press **Resume heating**.

### One-shot heat

There is a **One-shot heat** switch for every room and one for the whole home.

- **On:** the room heats to its *Target: one-shot heat*. Then the heater turns off,
  the switch turns itself off, and the normal mode logic takes over.
- **Off by hand:** cancels the one-shot heat.
- **Presence** does not affect one-shot heat, so you can start it remotely.
- **No power** (with a grid entity configured): the request becomes **Scheduled**
  and starts after power returns and the delay passes.
- **Power lost while heating:** the one-shot heat is cancelled.

## Room card

The integration adds the **HeatKeeper: room** card to every dashboard:
**Edit dashboard → Add card → HeatKeeper: room**.
If it is not in the list, reload the page bypassing the cache (Ctrl+Shift+R; in the mobile app:
Settings → Companion app → Reset frontend cache).

- Shows the room status and current target, e.g. "Heating · 21.0°".
- Optionally shows temperature, humidity and the presence switch.
- **Tap** opens the details, **hold** toggles one-shot heat.

```yaml
type: custom:heatkeeper-room-card
entity: sensor.heatkeeper_office_zone_status
show_temperature: false
show_humidity: false
show_presence: true
```

Full dashboard example: [`dashboards/heatkeeper.yaml`](dashboards/heatkeeper.yaml).

## Entities

Entity ids do not depend on the UI language. `<room>` is the room name as a slug
(Office → `office`, Кухня → `kukhnia`).

**HeatKeeper (global):**

| Entity | Description |
|---|---|
| `select.heatkeeper_mode` | Mode |
| `switch.heatkeeper_presence`, `switch.heatkeeper_presence_auto` | Presence: someone home / auto |
| `switch.heatkeeper_boost` | One-shot heat for the whole home |
| `button.heatkeeper_resume` | Resume heating after an outage |
| `number.heatkeeper_delta` | Hysteresis (±) |
| `time.heatkeeper_cheap_start`, `time.heatkeeper_cheap_end`, `number.heatkeeper_preheat_lead` | Cheap tariff: start, end, boost before end |
| `switch.heatkeeper_auto_restore`, `number.heatkeeper_restore_delay`, `number.heatkeeper_restore_stagger` | Outage: auto restore, delay, stagger |
| `sensor.heatkeeper_status`, `binary_sensor.heatkeeper_cheap_tariff`, `binary_sensor.heatkeeper_grid`, `sensor.heatkeeper_restore_at` | Status |

**Each room:**

| Entity | Description |
|---|---|
| `switch.heatkeeper_<room>_enabled` | Control enabled |
| `switch.heatkeeper_<room>_presence` | Presence (rooms with an owner only) |
| `switch.heatkeeper_<room>_day_heating` | Day heating |
| `switch.heatkeeper_<room>_boost` | One-shot heat |
| `number.heatkeeper_<room>_…_target` | Targets: maintain, night, pre-morning boost, day home/away, one-shot heat, after outage |
| `sensor.heatkeeper_<room>_zone_status`, `sensor.heatkeeper_<room>_zone_target` | Status and current target |

Settings survive Home Assistant restarts.

## Automation examples

**Phone → room presence:**

```yaml
automation:
  - alias: Office presence
    triggers:
      - trigger: state
        entity_id: person.me
    actions:
      - action: >-
          switch.turn_{{ 'on' if trigger.to_state.state == 'home' else 'off' }}
        target:
          entity_id: switch.heatkeeper_office_presence
```

**Zigbee button → one-shot heat** (Zigbee2MQTT example):

```yaml
automation:
  - alias: Bedroom heat button
    triggers:
      - trigger: state
        entity_id: event.bedroom_button_action
        attribute: event_type
        to: single
    actions:
      - action: switch.toggle
        target:
          entity_id: switch.heatkeeper_bedroom_boost
```

## Safety

- If a temperature sensor is unavailable, the room heater is switched off: HeatKeeper never heats blind.
- No commands are sent to an unavailable plug.
