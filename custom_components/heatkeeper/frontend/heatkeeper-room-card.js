/*
 * HeatKeeper room card.
 *
 * type: custom:heatkeeper-room-card
 * entity: sensor.heatkeeper_<room>_zone_status
 * name: optional override
 * show_temperature / show_humidity / show_presence: optional, default false
 *
 * Tap opens the room details, hold toggles the one-shot heat.
 */

const STRINGS = {
  en: {
    entity: "Room (HeatKeeper status sensor)",
    name: "Name (optional)",
    show_temperature: "Show temperature",
    show_humidity: "Show humidity",
    show_presence: "Show presence switch",
    hold_hint: "Hold to toggle one-shot heat",
    missing: "Entity not found",
    home: "Home",
    away: "Away",
  },
  uk: {
    entity: "Кімната (сенсор стану HeatKeeper)",
    name: "Назва (необовʼязково)",
    show_temperature: "Показувати температуру",
    show_humidity: "Показувати вологість",
    show_presence: "Показувати перемикач присутності",
    hold_hint: "Утримуйте, щоб увімкнути або вимкнути разовий нагрів",
    missing: "Сутність не знайдено",
    home: "Вдома",
    away: "Нікого",
  },
};

const HOLD_MS = 500;

function lang(hass) {
  const code = (hass && (hass.locale?.language || hass.language)) || "en";
  return STRINGS[code.split("-")[0]] ? code.split("-")[0] : "en";
}

function t(hass, key) {
  return STRINGS[lang(hass)][key] ?? STRINGS.en[key] ?? key;
}

function isZoneSensor(state) {
  return (
    state &&
    state.entity_id.startsWith("sensor.") &&
    state.attributes &&
    "boost_entity" in state.attributes
  );
}

const STATUS_STYLE = {
  heating: { color: "var(--state-climate-heat-color, #ff8100)", icon: "mdi:radiator" },
  boost: { color: "var(--state-climate-heat-color, #ff8100)", icon: "mdi:fire" },
  scheduled: { color: "var(--warning-color, #ffa600)", icon: "mdi:clock-outline" },
  blocked: { color: "var(--error-color, #db4437)", icon: "mdi:power-plug-off" },
  no_sensor: { color: "var(--error-color, #db4437)", icon: "mdi:thermometer-off" },
  disabled: { color: "var(--disabled-color, #bdbdbd)", icon: "mdi:radiator-off" },
  off: { color: "var(--disabled-color, #bdbdbd)", icon: "mdi:radiator-off" },
  day_off: { color: "var(--disabled-color, #bdbdbd)", icon: "mdi:radiator-disabled" },
  idle: { color: "var(--state-inactive-color, #7c8a95)", icon: "mdi:radiator" },
};

class HeatKeeperRoomCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: {
            entity: {
              filter: { integration: "heatkeeper", domain: "sensor", device_class: "enum" },
            },
          },
        },
        { name: "name", selector: { text: {} } },
        { name: "show_temperature", selector: { boolean: {} } },
        { name: "show_humidity", selector: { boolean: {} } },
        { name: "show_presence", selector: { boolean: {} } },
      ],
      computeLabel: (schema, _data, hass) => t(hass, schema.name),
    };
  }

  static getStubConfig(hass) {
    const zone = Object.values(hass.states).find(
      (s) => isZoneSensor(s) && s.entity_id.startsWith("sensor.heatkeeper_")
    );
    return { entity: zone ? zone.entity_id : "" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity is required");
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._config && (this._config.show_temperature || this._config.show_humidity) ? 2 : 1;
  }

  getGridOptions() {
    return { columns: 6, min_columns: 4, rows: this.getCardSize() };
  }

  connectedCallback() {
    this._render();
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        ha-card { height: 100%; box-sizing: border-box; padding: 10px 12px;
          cursor: pointer; user-select: none; -webkit-user-select: none;
          display: flex; flex-direction: column; justify-content: center; gap: 8px; }
        .row { display: flex; align-items: center; gap: 12px; min-width: 0; }
        .icon { flex: none; width: 36px; height: 36px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center; position: relative; }
        .icon::before { content: ""; position: absolute; inset: 0; border-radius: 50%;
          background: currentColor; opacity: 0.2; }
        .icon.active ha-icon { animation: pulse 2s ease-in-out infinite; }
        @keyframes pulse { 50% { opacity: 0.55; } }
        .text { flex: 1; min-width: 0; }
        .name { font-weight: 500; font-size: 14px; line-height: 20px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status { font-size: 12px; line-height: 16px; color: var(--secondary-text-color);
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
          overflow: hidden; }
        .chip { flex: none; display: flex; align-items: center; gap: 4px; padding: 4px 8px;
          border-radius: 16px; font-size: 12px; background: var(--secondary-background-color);
          color: var(--primary-text-color); }
        .chip.on { color: var(--state-active-color, var(--primary-color)); }
        .chip ha-icon { --mdc-icon-size: 16px; }
        .metrics { display: flex; gap: 16px; padding-left: 48px; font-size: 13px;
          color: var(--secondary-text-color); }
        .metrics span { display: flex; align-items: center; gap: 4px; }
        .metrics ha-icon { --mdc-icon-size: 16px; }
        .hidden { display: none !important; }
        .warning { color: var(--error-color); padding: 8px; }
      </style>
      <ha-card>
        <div class="row">
          <div class="icon"><ha-icon></ha-icon></div>
          <div class="text"><div class="name"></div><div class="status"></div></div>
          <div class="chip presence"><ha-icon></ha-icon><span></span></div>
        </div>
        <div class="metrics">
          <span class="temp"><ha-icon icon="mdi:thermometer"></ha-icon><b></b></span>
          <span class="hum"><ha-icon icon="mdi:water-percent"></ha-icon><b></b></span>
        </div>
      </ha-card>`;
    const card = root.querySelector("ha-card");
    card.addEventListener("pointerdown", (ev) => this._down(ev));
    card.addEventListener("pointerup", () => this._up());
    card.addEventListener("pointerleave", () => this._cancelHold());
    card.addEventListener("pointercancel", () => this._cancelHold());
    card.addEventListener("contextmenu", (ev) => ev.preventDefault());
    root.querySelector(".presence").addEventListener("pointerdown", (ev) => ev.stopPropagation());
    root.querySelector(".presence").addEventListener("pointerup", (ev) => {
      ev.stopPropagation();
      this._togglePresence();
    });
    this._els = {
      card,
      icon: root.querySelector(".icon"),
      iconEl: root.querySelector(".icon ha-icon"),
      name: root.querySelector(".name"),
      status: root.querySelector(".status"),
      presence: root.querySelector(".presence"),
      presenceIcon: root.querySelector(".presence ha-icon"),
      presenceText: root.querySelector(".presence span"),
      metrics: root.querySelector(".metrics"),
      temp: root.querySelector(".temp"),
      tempVal: root.querySelector(".temp b"),
      hum: root.querySelector(".hum"),
      humVal: root.querySelector(".hum b"),
    };
  }

  _down(ev) {
    if (ev.button !== undefined && ev.button !== 0) return;
    this._held = false;
    this._holdTimer = setTimeout(() => {
      this._held = true;
      this._toggleBoost();
    }, HOLD_MS);
  }

  _up() {
    const wasHeld = this._held;
    this._cancelHold();
    if (!wasHeld) this._moreInfo();
  }

  _cancelHold() {
    clearTimeout(this._holdTimer);
    this._holdTimer = undefined;
    this._held = false;
  }

  _moreInfo() {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId: this._config.entity },
      })
    );
  }

  _toggleBoost() {
    const state = this._hass?.states[this._config.entity];
    const boost = state?.attributes.boost_entity;
    if (!boost) return;
    if (navigator.vibrate) navigator.vibrate(50);
    this._hass.callService("switch", "toggle", { entity_id: boost });
  }

  _togglePresence() {
    const state = this._hass?.states[this._config.entity];
    const presence = state?.attributes.presence_entity;
    if (presence) this._hass.callService("switch", "toggle", { entity_id: presence });
  }

  _format(stateObj, fallback) {
    try {
      return this._hass.formatEntityState(stateObj);
    } catch (_err) {
      return fallback;
    }
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) this._build();
    const hass = this._hass;
    const cfg = this._config;
    const els = this._els;
    const state = hass.states[cfg.entity];

    if (!isZoneSensor(state)) {
      els.name.textContent = cfg.name || cfg.entity;
      els.status.textContent = t(hass, "missing");
      els.presence.classList.add("hidden");
      els.metrics.classList.add("hidden");
      return;
    }

    const a = state.attributes;
    const style = STATUS_STYLE[state.state] || STATUS_STYLE.idle;
    els.icon.style.color = style.color;
    els.iconEl.setAttribute("icon", style.icon);
    els.icon.classList.toggle("active", state.state === "heating" || state.state === "boost");
    els.name.textContent = cfg.name || a.zone_name || a.friendly_name;
    let status = this._format(state, state.state);
    if (a.target_temperature !== null && a.target_temperature !== undefined) {
      status += ` · ${Number(a.target_temperature).toFixed(1)}°`;
    }
    els.status.textContent = status;
    els.card.title = t(hass, "hold_hint");

    const presence = a.presence_entity ? hass.states[a.presence_entity] : undefined;
    const showPresence = cfg.show_presence && presence;
    els.presence.classList.toggle("hidden", !showPresence);
    if (showPresence) {
      const home = presence.state === "on";
      els.presence.classList.toggle("on", home);
      els.presenceIcon.setAttribute("icon", home ? "mdi:account" : "mdi:account-off-outline");
      els.presenceText.textContent = t(hass, home ? "home" : "away");
    }

    const showT = cfg.show_temperature && a.current_temperature !== null && a.current_temperature !== undefined;
    const showH = cfg.show_humidity && a.current_humidity !== null && a.current_humidity !== undefined;
    els.metrics.classList.toggle("hidden", !(showT || showH));
    els.temp.classList.toggle("hidden", !showT);
    els.hum.classList.toggle("hidden", !showH);
    if (showT) els.tempVal.textContent = `${Number(a.current_temperature).toFixed(1)} °C`;
    if (showH) els.humVal.textContent = `${Math.round(Number(a.current_humidity))} %`;
  }
}

if (!customElements.get("heatkeeper-room-card")) {
  customElements.define("heatkeeper-room-card", HeatKeeperRoomCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "heatkeeper-room-card",
    name: "HeatKeeper: room",
    description: "Room heating status; hold to toggle one-shot heat.",
    preview: true,
  });
}
