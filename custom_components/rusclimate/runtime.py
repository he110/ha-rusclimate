"""Resources shared by all config entries: one UDP socket, one cloud MQTT session, one mDNS browser."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.ssl import get_default_context
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .api.cloud import CloudChannel, CloudHub
from .api.local import LocalChannel, UdpHub
from .api.router import Breezer
from .const import DOMAIN, MDNS_TYPE

_LOGGER = logging.getLogger(__name__)


@dataclass
class RuntimeData:
    breezer: Breezer


type RusclimateConfigEntry = ConfigEntry[RuntimeData]


def tz_offset_minutes() -> int:
    offset = dt_util.now().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


class Shared:
    """Lives in hass.data[DOMAIN] while at least one entry is loaded."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.udp = UdpHub()
        self.cloud = CloudHub(get_default_context())
        self._locals: dict[str, LocalChannel] = {}
        self._endpoints: dict[str, tuple[str, int, dict[str, Any]]] = {}
        self._browser: AsyncServiceBrowser | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.users = 0

    @classmethod
    def get(cls, hass: HomeAssistant) -> Shared:
        if (shared := hass.data.get(DOMAIN)) is None:
            shared = hass.data[DOMAIN] = cls(hass)
        return shared

    def local_channel(self, mac: str, token: str) -> LocalChannel:
        channel = LocalChannel(mac, token, self.udp, tz_offset_minutes)
        self._locals[mac] = channel
        if endpoint := self._endpoints.get(mac):
            channel.update_endpoint(*endpoint)
        return channel

    def cloud_channel(self, device_type: int, token: str) -> CloudChannel:
        return CloudChannel(device_type, token, self.cloud)

    def forget(self, mac: str) -> None:
        self._locals.pop(mac, None)

    async def acquire(self) -> None:
        self.users += 1
        if self._browser is None:
            aiozc = await zeroconf.async_get_async_instance(self.hass)
            self._browser = AsyncServiceBrowser(aiozc.zeroconf, [MDNS_TYPE], handlers=[self._on_service])

    async def release(self) -> None:
        self.users -= 1
        if self.users > 0:
            return
        if self._browser is not None:
            await self._browser.async_cancel()
            self._browser = None
        for task in self._tasks:
            task.cancel()
        await self.cloud.stop()
        self.udp.stop()
        self.hass.data.pop(DOMAIN, None)

    def _on_service(
        self, zeroconf: Any, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            task = self.hass.async_create_background_task(
                self._resolve(zeroconf, service_type, name), f"{DOMAIN} resolve {name}"
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _resolve(self, zc: Any, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(zc, 3000) or not info.parsed_addresses() or info.port is None:
            return
        txt = {k: v for k, v in info.decoded_properties.items() if v is not None}
        mac = str(txt.get("macaddr") or txt.get("mac") or name.split(".")[0]).replace(":", "").lower()
        endpoint = (info.parsed_addresses()[0], info.port, txt)
        self._endpoints[mac] = endpoint
        if channel := self._locals.get(mac):
            channel.update_endpoint(*endpoint)
