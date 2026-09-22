"""Channel selection: Auto / Local / Cloud. No Home Assistant imports.

Auto prefers local and falls back to cloud; the idea comes from XiaoMi/ha_xiaomi_home (per-channel
online registry, device available if any channel is) and AlexxIT/YandexStation (drop to cloud the
moment the local session dies, return when it is back).

State rule: the active channel is the source of truth. A key the active channel never reports
(cloud-only diagnostics such as RSSI latency) may still come from the other channel.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from . import params as p
from .channel import Channel, ChannelError

_LOGGER = logging.getLogger(__name__)

ECHO_TIMEOUT = 3.0

Listener = Callable[[set[str]], None]

CONNECTION_KEY = "_connection"  # pseudo-key notified when the active channel changes


class ConnMode(StrEnum):
    AUTO = "auto"
    LOCAL = "local"
    CLOUD = "cloud"


class NotAvailable(Exception):
    """No channel can reach the device right now."""


class Breezer:
    def __init__(self, mode: ConnMode, local: Channel | None, cloud: Channel | None) -> None:
        self.mode = mode
        self.local = local if mode in (ConnMode.AUTO, ConnMode.LOCAL) else None
        self.cloud = cloud if mode in (ConnMode.AUTO, ConnMode.CLOUD) else None
        self.state: dict[str, Any] = {}
        self.last_on_mode: int = p.Mode.MANUAL
        self._listeners: list[Listener] = []
        self._active: Channel | None = None
        self._echo: dict[str, tuple[Any, asyncio.Future[None]]] = {}
        self.fallback_sends = 0
        for channel in self.channels:
            channel.bind(self._on_update, self._on_channel_state)

    @property
    def channels(self) -> list[Channel]:
        return [c for c in (self.local, self.cloud) if c is not None]

    @property
    def active(self) -> Channel | None:
        return self._active

    @property
    def available(self) -> bool:
        return self._active is not None

    async def start(self) -> None:
        for channel in self.channels:
            await channel.start()
        self._reselect()

    async def stop(self) -> None:
        for channel in self.channels:
            await channel.stop()
        for _, fut in self._echo.values():
            fut.cancel()
        self._echo.clear()

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def send(self, key: str, value: Any) -> None:
        """Write one parameter. In Auto, a write the device does not echo back within
        ECHO_TIMEOUT is retried once through the other channel."""
        primary = self._active
        if primary is None:
            raise NotAvailable
        if self.state.get(key) == value:
            await self._send_via(primary, key, value)
            return
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._echo[key] = (value, fut)
        try:
            try:
                await self._send_via(primary, key, value)
            except ChannelError:
                if not (fallback := self._fallback_for(primary)):
                    raise
                self.fallback_sends += 1
                await self._send_via(fallback, key, value)
                return
            if self.mode is not ConnMode.AUTO:
                return
            try:
                await asyncio.wait_for(asyncio.shield(fut), ECHO_TIMEOUT)
            except TimeoutError:
                if fallback := self._fallback_for(primary):
                    _LOGGER.info("No echo for %s via %s, retrying via %s", key, primary.name, fallback.name)
                    self.fallback_sends += 1
                    await self._send_via(fallback, key, value)
        finally:
            if self._echo.get(key, (None, None))[1] is fut:
                del self._echo[key]

    def _fallback_for(self, channel: Channel) -> Channel | None:
        if self.mode is not ConnMode.AUTO:
            return None
        other = self.cloud if channel is self.local else self.local
        return other if other is not None and other.available else None

    @staticmethod
    async def _send_via(channel: Channel, key: str, value: Any) -> None:
        _LOGGER.debug("Send %s=%r via %s", key, value, channel.name)
        await channel.send(key, value)

    def _on_update(self, channel: Channel, changes: dict[str, Any]) -> None:
        active = self._active
        if channel is not active:
            # Only fill in keys the active channel does not know about.
            known = active.snapshot if active is not None else {}
            changes = {k: v for k, v in changes.items() if k not in known}
        self._apply(changes)

    def _on_channel_state(self, channel: Channel) -> None:
        self._reselect()

    def _reselect(self) -> None:
        new = next((c for c in self.channels if c.available), None)
        if new is self._active:
            return
        _LOGGER.debug("Active channel: %s -> %s", self._active and self._active.name, new and new.name)
        self._active = new
        changed = {CONNECTION_KEY}
        if new is not None:
            changed |= self._merge(new.snapshot)
        self._notify(changed)

    def _apply(self, changes: dict[str, Any]) -> None:
        if changed := self._merge(changes):
            self._notify(changed)

    def _merge(self, changes: dict[str, Any]) -> set[str]:
        changed = {k for k, v in changes.items() if self.state.get(k, _MISSING) != v}
        for key in changed:
            value = changes[key]
            self.state[key] = value
            if key == p.MODE and value != p.Mode.OFF:
                self.last_on_mode = value
            if (pending := self._echo.get(key)) and pending[0] == value and not pending[1].done():
                pending[1].set_result(None)
        return changed

    def _notify(self, changed: set[str]) -> None:
        for listener in list(self._listeners):
            try:
                listener(changed)
            except Exception:
                _LOGGER.exception("Listener failed")

    def diagnostics(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "active": self._active.name if self._active else None,
            "fallback_sends": self.fallback_sends,
            "last_on_mode": self.last_on_mode,
            "channels": {c.name: c.diagnostics() for c in self.channels},
        }


_MISSING = object()
