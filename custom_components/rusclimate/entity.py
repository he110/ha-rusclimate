"""Base entity: push updates from the Breezer router, filtered by the keys each entity cares about."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity

from .api import params as p
from .api.channel import ChannelError
from .api.router import CONNECTION_KEY, NotAvailable
from .api.share_link import format_mac
from .const import CONF_DEVICE_TYPE, CONF_MAC, CONF_ROOM, DOMAIN, MANUFACTURER, MODELS
from .runtime import RusclimateConfigEntry


class RusclimateEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    # Parameters whose change should re-render this entity. The active-channel pseudo-key is
    # always included, because it drives availability.
    _watch: frozenset[str] = frozenset()

    def __init__(self, entry: RusclimateConfigEntry, key: str) -> None:
        self.breezer = entry.runtime_data.breezer
        mac = entry.data[CONF_MAC]
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(mac))},
            manufacturer=MANUFACTURER,
            model=MODELS.get(entry.data[CONF_DEVICE_TYPE], f"Device type {entry.data[CONF_DEVICE_TYPE]}"),
            translation_key="breezer",
            suggested_area=entry.data.get(CONF_ROOM),
            sw_version=self.breezer.state.get(p.FIRMWARE),
        )

    @property
    def state_data(self) -> dict[str, Any]:
        return self.breezer.state

    @property
    def available(self) -> bool:
        return self.breezer.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.breezer.add_listener(self._on_breezer_update))

    def _on_breezer_update(self, changed: set[str]) -> None:
        if CONNECTION_KEY in changed or changed & self._watch:
            self.async_write_ha_state()

    async def _send(self, key: str, value: Any) -> None:
        try:
            await self.breezer.send(key, value)
        except NotAvailable as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_available") from err
        except ChannelError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"error": str(err)},
            ) from err
