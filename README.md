# Rusclimate (Hommyn) for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/he110/ha-rusclimate/actions/workflows/validate.yaml/badge.svg)](https://github.com/he110/ha-rusclimate/actions/workflows/validate.yaml)
[![Tests](https://github.com/he110/ha-rusclimate/actions/workflows/tests.yaml/badge.svg)](https://github.com/he110/ha-rusclimate/actions/workflows/tests.yaml)
[![Release](https://img.shields.io/github/v/release/he110/ha-rusclimate)](https://github.com/he110/ha-rusclimate/releases)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=he110&repository=ha-rusclimate&category=integration)
[![Open your Home Assistant instance and start setting up Rusclimate.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=rusclimate)

Control Rusclimate devices managed by the **Hommyn** app (Ballu, Electrolux and others sold by
Rusclimate) directly from Home Assistant: over your **local network**, through the **vendor cloud**,
or both with automatic fallback.

The first supported device is the **Ballu ONEAIR ASP-100 / Electrolux EASP-100** breezer
(Hommyn device type 69).

[Русская версия](README.ru.md)

## Features

- **Two channels, one device.** Local UDP (the same encrypted protocol the app uses on your Wi-Fi)
  and the vendor's MQTT cloud. Both deliver changes within a fraction of a second.
- **Connection mode per device:**
  - **Auto** (default) — local first; if the local session drops, commands and state switch to the
    cloud at once and come back when the local channel recovers. A command that is not confirmed by
    the device within 3 seconds is retried once through the other channel.
  - **Local only** — never talks to the cloud; works without internet.
  - **Cloud only** — for devices on another network.
- The Hommyn app keeps working alongside Home Assistant.
- Devices on your network are discovered automatically.

## Entities (ASP-100)

| Entity | What it does |
|---|---|
| Climate | On/off, presets (manual, night, turbo, ventilation; auto only when a CO₂ sensor is fitted), fan speed 1–7, heater set point 5–25 °C. Switching on restores the last mode, like the app. |
| Supply air temperature | Air temperature after the heater |
| CO₂ | Only available when the optional sensor is fitted |
| Filter | Remaining filter resource, % |
| Turbo ends | When the 15-minute turbo run finishes |
| Sound | Built-in ambient sounds: rain, sea, forest, birds, fireplace |
| Button sound, Backlight auto-off | Device settings |
| Problem | On when the device reports an error code |
| Connection | Which channel carries the device now: local, cloud or offline (diagnostic) |
| Signal strength | Wi-Fi RSSI (diagnostic, disabled by default) |

## Requirements

- Home Assistant 2026.9 or newer.
- For the local channel: Home Assistant and the device on the same network segment (mDNS must reach
  Home Assistant).

## Installation

HACS → ⋮ → Custom repositories → add this repository as an *Integration* → install
**Rusclimate (Hommyn)** → restart Home Assistant.

## Setup

1. In the Hommyn app open the device → **Settings → Access control → Share** and press **Share**
   under the QR code. Copy the link — it looks like
   `rusklimat://device-share/rusclimate/69/<mac>?token=…`.
2. In Home Assistant: **Settings → Devices & services**. A discovered device shows up there — press
   **Add** and paste its link. Or use **Add integration → Rusclimate (Hommyn)**.
3. Choose the connection mode.

One share link per device. The room from the link becomes the device's suggested area.

## Options

**Configure** on the integration entry changes the connection mode. **Reconfigure** accepts a new share
link for the same device (for example after the device was re-added in the app).

## Using it

```yaml
automation:
  - alias: "Breezer: night mode at 23:00"
    triggers:
      - trigger: time
        at: "23:00:00"
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.bedroom_breezer
        data:
          preset_mode: night
```

## Security and privacy

- **The share link is a password.** Its token alone lets anyone control the device through the vendor
  cloud. Home Assistant stores it in the config entry; diagnostics redact it.
- The cloud channel logs in with the Hommyn app's built-in credentials (the same for every app user)
  and a unique client id, exactly as the app does. The local channel needs no internet.
- Commands are never sent as retained MQTT messages.

## Troubleshooting

- **Connection shows "cloud" in Auto** — Home Assistant does not see the device's mDNS announcement
  (`_syncleo._udp`). Check that both are on the same network segment and multicast is not filtered.
- **Device unavailable in Cloud only after an HA restart** — the vendor broker keeps a stale "offline"
  flag for some devices until the device sends a fresh update; change anything on the device or use
  Auto.
- Download diagnostics from the device page when reporting an issue.

## How it works

The device announces itself over mDNS; its UDP port and X25519 key change on every reboot, so the
integration follows the announcements and reconnects. The local session (X25519 + AES-CBC, built on
[pysyncleo](https://github.com/DeKaN/pysyncleo)) and the cloud MQTT session both push state; in Auto
the active channel is the source of truth and the other one fills in only what the active channel does
not report (for example Wi-Fi latency from the cloud).

Thanks to the community in [Hommyn/local_mqtt#1](https://github.com/Hommyn/local_mqtt/issues/1),
[DeKaN/pysyncleo](https://github.com/DeKaN/pysyncleo), [DeKaN/ha-syncleo](https://github.com/DeKaN/ha-syncleo)
and [alimp01/hass-hommyn](https://github.com/alimp01/hass-hommyn), who mapped the protocols.

## Development

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest tests -q
```

`custom_components/rusclimate/api/` has no Home Assistant imports and is tested on its own in
`tests/pure`.

## License

MIT
