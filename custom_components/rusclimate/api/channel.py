"""Transport-agnostic channel contract. No Home Assistant imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

UpdateCallback = Callable[["Channel", dict[str, Any]], None]
StateCallback = Callable[["Channel"], None]


class ChannelError(Exception):
    """A command could not be handed to the transport."""


class Channel(ABC):
    """One way of reaching one device (local UDP or cloud MQTT).

    A channel keeps its own ``snapshot`` of everything it has heard from the device, so the router
    can switch to it and immediately have a complete state instead of waiting for fresh pushes.
    """

    name: str

    def __init__(self) -> None:
        self.snapshot: dict[str, Any] = {}
        self._on_update: UpdateCallback | None = None
        self._on_state: StateCallback | None = None

    def bind(self, on_update: UpdateCallback, on_state: StateCallback) -> None:
        self._on_update = on_update
        self._on_state = on_state

    @property
    @abstractmethod
    def available(self) -> bool:
        """The device is reachable through this channel right now."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, key: str, value: Any) -> None:
        """Hand a write to the transport. Raises ChannelError if that is impossible."""

    def diagnostics(self) -> dict[str, Any]:
        return {"available": self.available}

    def _emit(self, changes: dict[str, Any]) -> None:
        changed = {k: v for k, v in changes.items() if self.snapshot.get(k, _MISSING) != v}
        if not changed:
            return
        self.snapshot.update(changed)
        if self._on_update:
            self._on_update(self, changed)

    def _emit_state(self) -> None:
        if self._on_state:
            self._on_state(self)


_MISSING = object()
