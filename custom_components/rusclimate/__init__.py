"""Rusclimate / Hommyn devices (Ballu, Electrolux breezers) over local UDP and the vendor cloud."""

from __future__ import annotations

from functools import partial

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .api import params as p
from .api.router import Breezer, ConnMode
from .const import CONF_CONN_MODE, CONF_DEVICE_TYPE, CONF_MAC, CONF_TOKEN, DOMAIN
from .health import LocalHealthMonitor
from .runtime import RuntimeData, RusclimateConfigEntry, Shared

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: RusclimateConfigEntry) -> bool:
    shared = Shared.get(hass)
    await shared.acquire()
    mac, token = entry.data[CONF_MAC], entry.data[CONF_TOKEN]
    mode = ConnMode(entry.options.get(CONF_CONN_MODE, ConnMode.AUTO))
    breezer = Breezer(
        mode,
        local=shared.local_channel(mac, token) if mode is not ConnMode.CLOUD else None,
        cloud=shared.cloud_channel(entry.data[CONF_DEVICE_TYPE], token)
        if mode is not ConnMode.LOCAL
        else None,
    )
    # Push-based: no first refresh to wait for. Entities show unavailable until a channel is up.
    await breezer.start()
    entry.runtime_data = RuntimeData(breezer=breezer)
    entry.async_on_unload(breezer.add_listener(partial(_sync_firmware, hass, entry)))
    entry.async_on_unload(LocalHealthMonitor(hass, entry, breezer).start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _sync_firmware(hass: HomeAssistant, entry: RusclimateConfigEntry, changed: set[str]) -> None:
    if p.FIRMWARE not in changed:
        return
    registry = dr.async_get(hass)
    if device := registry.async_get_device_by_identifier((DOMAIN, entry.data[CONF_MAC]), entry.entry_id):
        registry.async_update_device(device.id, sw_version=entry.runtime_data.breezer.state[p.FIRMWARE])


async def async_unload_entry(hass: HomeAssistant, entry: RusclimateConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        shared = Shared.get(hass)
        await entry.runtime_data.breezer.stop()
        shared.forget(entry.data[CONF_MAC])
        await shared.release()
    return unloaded
