"""Home Assistant tests: fake channels instead of UDP/MQTT, mocked zeroconf."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rusclimate.api import params as p
from custom_components.rusclimate.api.channel import Channel, ChannelError
from custom_components.rusclimate.api.router import ConnMode
from custom_components.rusclimate.const import CONF_CONN_MODE, DOMAIN

MAC = "aabbccddeeff"
TOKEN = "fedcba9876543210fedcba9876543210"
LINK = (
    f"rusklimat://device-share/rusclimate/69/{MAC}?token={TOKEN}"
    "&name=Ballu%20ONEAIR%20ASP-100&deviceLocation=Home&deviceRoom=Office&attributes_model=ballu_asp"
)

# Snapshot the office breezer reported live (heater fitted, no CO2 sensor).
LIVE_STATE: dict[str, Any] = {
    p.MODE: 1,
    p.SPEED: 2,
    p.TARGET_TEMPERATURE: 5.0,
    p.CURRENT_TEMPERATURE: 17.0,
    p.CO2: 0,
    p.EXPENDABLES: [76],
    p.MELODY: 0,
    p.BUTTON_SOUND: True,
    p.BACKLIGHT_AUTO_OFF: False,
    p.TURBO_TIME: 0,
    p.PROGRAM_DATA_0: b"\x01\x00",
    p.PROGRAM_DATA_1: b"\x00\x00\x00",
    p.ERROR_CODE: 0,
    p.FIRMWARE: "1.38",
}


class FakeChannel(Channel):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.up = False
        self.echo = True
        self.sent: list[tuple[str, Any]] = []

    @property
    def available(self) -> bool:
        return self.up

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, key: str, value: Any) -> None:
        if not self.up:
            raise ChannelError("down")
        self.sent.append((key, value))
        if self.echo:
            asyncio.get_running_loop().call_soon(self._emit, {key: value})

    def set_up(self, up: bool) -> None:
        self.up = up
        self._emit_state()

    def push(self, changes: dict[str, Any]) -> None:
        self._emit(changes)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture(autouse=True)
def _zeroconf(mock_async_zeroconf):
    browser = MagicMock()
    browser.return_value.async_cancel = AsyncMock()
    with patch("custom_components.rusclimate.runtime.AsyncServiceBrowser", browser):
        yield


@pytest.fixture
def channels():
    """Patch the shared runtime to hand out fake channels. Returns {"local": ..., "cloud": ...}."""
    made: dict[str, FakeChannel] = {}

    def local(self, mac, token):
        return made.setdefault("local", FakeChannel("local"))

    def cloud(self, device_type, token):
        return made.setdefault("cloud", FakeChannel("cloud"))

    with (
        patch("custom_components.rusclimate.runtime.Shared.local_channel", local),
        patch("custom_components.rusclimate.runtime.Shared.cloud_channel", cloud),
    ):
        yield made


def make_entry(mode: ConnMode = ConnMode.AUTO) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Office",
        unique_id=MAC,
        data={"mac": MAC, "device_type": 69, "token": TOKEN, "room": "Office"},
        options={CONF_CONN_MODE: mode.value},
    )


@pytest.fixture
async def loaded(hass, channels):
    """Entry loaded in Auto with the local channel up and the live snapshot pushed."""
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    local = channels["local"]
    local.push(dict(LIVE_STATE))
    local.set_up(True)
    await hass.async_block_till_done()
    return entry, channels
