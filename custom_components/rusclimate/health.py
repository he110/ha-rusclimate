"""Repair issue: tell the user when a device has not been reachable over the local network for a while.

In Auto the breezer keeps working through the cloud, so a broken local path (mDNS filtered, device
moved to another VLAN, firmware change) would otherwise go unnoticed until the internet goes down.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from .api.router import CONNECTION_KEY, Breezer
from .const import DOMAIN
from .runtime import RusclimateConfigEntry

# Long enough to ride out device reboots and Wi-Fi roaming; short enough to notice the same day.
LOCAL_DOWN_GRACE = timedelta(minutes=30)


def issue_id(entry: RusclimateConfigEntry) -> str:
    return f"local_unreachable_{entry.entry_id}"


class LocalHealthMonitor:
    def __init__(self, hass: HomeAssistant, entry: RusclimateConfigEntry, breezer: Breezer) -> None:
        self._hass = hass
        self._entry = entry
        self._breezer = breezer
        self._cancel_timer: CALLBACK_TYPE | None = None

    @callback
    def start(self) -> CALLBACK_TYPE:
        """Begin watching; returns the unsubscribe callback for entry.async_on_unload."""
        if self._breezer.local is None:
            return lambda: None
        remove_listener = self._breezer.add_listener(self._on_update)
        self._evaluate()

        @callback
        def stop() -> None:
            remove_listener()
            self._stop_timer()
            ir.async_delete_issue(self._hass, DOMAIN, issue_id(self._entry))

        return stop

    @callback
    def _on_update(self, changed: set[str]) -> None:
        if CONNECTION_KEY in changed:
            self._evaluate()

    @callback
    def _evaluate(self) -> None:
        local = self._breezer.local
        if local is not None and local.available:
            self._stop_timer()
            ir.async_delete_issue(self._hass, DOMAIN, issue_id(self._entry))
        elif self._cancel_timer is None:
            self._cancel_timer = async_call_later(self._hass, LOCAL_DOWN_GRACE, self._raise)

    @callback
    def _raise(self, _now: object) -> None:
        self._cancel_timer = None
        local = self._breezer.local
        if local is None or local.available:
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id(self._entry),
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="local_unreachable_cloud"
            if self._breezer.active is not None
            else "local_unreachable",
            translation_placeholders={"name": self._entry.title},
        )

    @callback
    def _stop_timer(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
