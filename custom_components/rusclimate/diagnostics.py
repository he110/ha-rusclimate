"""Diagnostics: per-channel health and the last known device state. The share token is redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, CONF_TOKEN
from .runtime import RusclimateConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_MAC, "mac", "last_wifi", "diag/chip"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RusclimateConfigEntry
) -> dict[str, Any]:
    breezer = entry.runtime_data.breezer
    state = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in breezer.state.items()}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "router": breezer.diagnostics(),
        "state": async_redact_data(state, TO_REDACT),
    }
