"""Device parameters shared by both transports. No Home Assistant imports.

Keys are the cloud MQTT topic suffixes (``rusclimate/<type>/<token>/state/<key>``); the local UDP
channel maps its commands onto the same keys, so everything above the transports speaks one
vocabulary. Values are normalised Python types, not the wire strings.

Verified live on Ballu ONEAIR ASP-100 (device type 69), module firmware 1.38 — see DESIGN.md.
"""

from __future__ import annotations

import json
from enum import IntEnum
from typing import Any

MODE = "mode"
SPEED = "speed"
TARGET_TEMPERATURE = "temperature"
CURRENT_TEMPERATURE = "sensor/temperature"
CO2 = "sensor/co2"
EXPENDABLES = "expendables"  # filter resource, list of percentages
MELODY = "amount"
BUTTON_SOUND = "volume"
BACKLIGHT_AUTO_OFF = "backlight"
TURBO_TIME = "time"  # seconds left in turbo; ticks every second while turbo runs
PROGRAM_DATA_0 = "program_data/0"  # [heater installed, CO2 sensor installed]
PROGRAM_DATA_1 = "program_data/1"  # [turn on, night speed, damper]
ERROR_CODE = "error/code"
RSSI = "diag/rssi"
FIRMWARE = "firmware"


class Mode(IntEnum):
    OFF = 0
    MANUAL = 1
    AUTO = 2  # driven by the CO2 sensor; the device refuses it when no sensor is installed
    NIGHT = 3
    TURBO = 4
    VENTILATION = 5


SPEED_MIN = 1
SPEED_MAX = 7
TEMPERATURE_MIN = 5
TEMPERATURE_MAX = 25

_INT_KEYS = {MODE, SPEED, CO2, MELODY, TURBO_TIME, RSSI}
_FLOAT_KEYS = {TARGET_TEMPERATURE, CURRENT_TEMPERATURE}
_BOOL_KEYS = {BUTTON_SOUND, BACKLIGHT_AUTO_OFF}
_BYTES_KEYS = {PROGRAM_DATA_0, PROGRAM_DATA_1}

# Keys we are allowed to write. Anything else is read-only.
WRITABLE = {MODE, SPEED, TARGET_TEMPERATURE, MELODY, BUTTON_SOUND, BACKLIGHT_AUTO_OFF}


def decode_cloud(key: str, raw: str) -> Any:
    """Wire string from the cloud broker -> normalised value. Raises ValueError on garbage."""
    raw = raw.strip()
    if key in _INT_KEYS:
        return int(float(raw))
    if key in _FLOAT_KEYS:
        return float(raw)
    if key in _BOOL_KEYS:
        return raw.lower() in ("1", "true", "on")
    if key in _BYTES_KEYS:
        return bytes.fromhex(raw)
    if key == EXPENDABLES:
        return [int(v) for v in json.loads(raw)]
    if key == ERROR_CODE:
        return int(raw, 16)
    return raw


def encode_cloud(key: str, value: Any) -> str:
    """Normalised value -> wire string for ``control/<key>``."""
    if key in _BOOL_KEYS:
        return "1" if value else "0"
    if key in _BYTES_KEYS:
        return bytes(value).hex()
    if key == TARGET_TEMPERATURE:
        return str(round(value))
    return str(int(value))


def program_flag(state: dict[str, Any], key: str, offset: int) -> bool | None:
    data = state.get(key)
    if not isinstance(data, (bytes, bytearray)) or len(data) <= offset:
        return None
    return data[offset] == 1


def heater_installed(state: dict[str, Any]) -> bool | None:
    return program_flag(state, PROGRAM_DATA_0, 0)


def co2_sensor_installed(state: dict[str, Any]) -> bool | None:
    return program_flag(state, PROGRAM_DATA_0, 1)


def filter_percent(state: dict[str, Any]) -> int | None:
    value = state.get(EXPENDABLES)
    return value[0] if isinstance(value, list) and value else None
