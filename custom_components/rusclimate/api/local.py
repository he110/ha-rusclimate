"""Local channel: Syncleo UDP protocol via pysyncleo. No Home Assistant imports.

Discovery is the caller's job: the device advertises ``_syncleo._udp.local.`` and its UDP port and
X25519 public key change on every reboot, so the caller feeds fresh mDNS data into
``LocalChannel.update_endpoint``. One ``UdpHub`` (one socket) serves all devices.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from pysyncleo.commands import (
    CmdAmount,
    CmdBacklight,
    CmdInitDiagnostic,
    CmdMode,
    CmdProgramData,
    CmdSpeed,
    CmdTargetTemperature,
    CmdTimeSync,
    CmdVolume,
    UdpCommand,
)
from pysyncleo.enums import ConnectionState, UdpCommandType
from pysyncleo.models import DiagnosticStatus, SyncleoUdpDevice
from pysyncleo.transport import SyncleoConnection

from . import params as p
from .channel import Channel, ChannelError

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 5.0
RECONNECT_MAX = 300.0


class _Connection(SyncleoConnection):
    """pysyncleo 0.4.0 syncs time with a zero UTC offset on every connect, which silently resets
    the device's timezone (seen live: cloud ``timezone`` flips 180 -> 0). Send the real offset."""

    def __init__(self, *args: Any, tz_offset: Callable[[], int], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tz_offset = tz_offset

    async def _run_initialization(self, mode: int) -> None:
        await asyncio.sleep(0.5)
        await self.send_command(CmdTimeSync(int(time.time()), self._tz_offset()))
        if mode == 1:
            await asyncio.sleep(0.2)
            await self.send_command(CmdInitDiagnostic())


class UdpHub(asyncio.DatagramProtocol):
    """One UDP socket shared by all local channels; routes datagrams by source address."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self._conns: dict[tuple[str, int], SyncleoConnection] = {}

    async def start(self) -> None:
        if self.transport is None:
            loop = asyncio.get_running_loop()
            await loop.create_datagram_endpoint(lambda: self, local_addr=("0.0.0.0", 0))  # noqa: S104

    def stop(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if conn := self._conns.get((addr[0], addr[1])):
            conn.feed_datagram(data)

    def attach(self, conn: SyncleoConnection) -> None:
        self._conns[conn.device.inet_address] = conn

    def detach(self, conn: SyncleoConnection) -> None:
        if self._conns.get(conn.device.inet_address) is conn:
            del self._conns[conn.device.inet_address]


def decode_udp(cmd: UdpCommand) -> dict[str, Any]:
    """Incoming UDP command -> {param key: normalised value}."""
    match cmd.command_type:
        case UdpCommandType.MODE:
            return {p.MODE: int(cmd.value)}
        case UdpCommandType.SPEED:
            return {p.SPEED: int(cmd.value)}
        case UdpCommandType.TARGET_TEMPERATURE:
            return {p.TARGET_TEMPERATURE: float(cmd.value)}
        case UdpCommandType.TEMPERATURE:
            return {p.CURRENT_TEMPERATURE: float(cmd.value)}
        case UdpCommandType.CO2:
            return {p.CO2: int(cmd.value)}
        case UdpCommandType.EXPENDABLES:
            return {p.EXPENDABLES: [int(v) for v in cmd.value]}
        case UdpCommandType.AMOUNT:
            return {p.MELODY: int(cmd.value)}
        case UdpCommandType.VOLUME:
            return {p.BUTTON_SOUND: bool(cmd.value)}
        case UdpCommandType.BACKLIGHT:
            return {p.BACKLIGHT_AUTO_OFF: bool(cmd.value)}
        case UdpCommandType.TARGET_TIME:
            return {p.TURBO_TIME: int(cmd.value)}
        case UdpCommandType.ERROR:
            return {p.ERROR_CODE: int(cmd.value)}
        case UdpCommandType.PROGRAM_DATA:
            raw = bytes(cmd.value or b"")
            return {f"program_data/{raw[0]}": raw[1:]} if raw else {}
        case UdpCommandType.DIAGNOSTIC if isinstance(cmd.value, DiagnosticStatus):
            rssi = cmd.value.rssi  # unsigned byte on the wire
            return {p.RSSI: rssi - 256 if rssi > 127 else rssi}
    return {}


def encode_udp(key: str, value: Any) -> UdpCommand:
    match key:
        case p.MODE:
            return CmdMode(int(value))
        case p.SPEED:
            return CmdSpeed(int(value))
        case p.TARGET_TEMPERATURE:
            return CmdTargetTemperature(float(value))
        case p.MELODY:
            return CmdAmount(int(value))
        case p.BUTTON_SOUND:
            return CmdVolume(bool(value))
        case p.BACKLIGHT_AUTO_OFF:
            return CmdBacklight(bool(value))
        case p.PROGRAM_DATA_0 | p.PROGRAM_DATA_1:
            return CmdProgramData(bytes(value), mode=int(key.rsplit("/", 1)[1]))
    raise ChannelError(f"parameter {key} is not writable over UDP")


class LocalChannel(Channel):
    name = "local"

    def __init__(self, mac: str, token: str, hub: UdpHub, tz_offset: Callable[[], int]) -> None:
        super().__init__()
        self.mac = mac
        self._token = token
        self._hub = hub
        self._tz_offset = tz_offset
        self._endpoint: tuple[str, int, dict[str, Any]] | None = None
        self._conn: _Connection | None = None
        self._reconnect: asyncio.TimerHandle | None = None
        self._backoff = RECONNECT_MIN
        self._running = False
        self.connects = 0
        self.last_connected: float | None = None

    @property
    def available(self) -> bool:
        return self._conn is not None and self._conn.state == ConnectionState.CONNECTED

    @property
    def host(self) -> str | None:
        return self._endpoint[0] if self._endpoint else None

    async def start(self) -> None:
        self._running = True
        await self._hub.start()
        if self._endpoint:
            self._connect()

    async def stop(self) -> None:
        self._running = False
        self._cancel_reconnect()
        self._drop()

    def update_endpoint(self, host: str, port: int, txt: dict[str, Any]) -> None:
        """Fresh mDNS data. Reconnect if the address or key moved (device rebooted) or we are down."""
        new = (host, port, dict(txt))
        moved = (
            self._endpoint is None
            or self._endpoint[:2] != new[:2]
            or (self._endpoint[2].get("public") != txt.get("public"))
        )
        self._endpoint = new
        if firmware := txt.get("firmware"):
            self._emit({p.FIRMWARE: str(firmware)})
        idle = self._conn is None or self._conn.state in (
            ConnectionState.DISCONNECTED,
            ConnectionState.NOT_CONNECTED,
        )
        # A re-announce while a handshake is in flight must not restart it.
        if self._running and (moved or idle):
            self._backoff = RECONNECT_MIN
            self._connect()

    async def send(self, key: str, value: Any) -> None:
        if not self.available or self._conn is None:
            raise ChannelError("local channel is not connected")
        await self._conn.send_command(encode_udp(key, value))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "host": self.host,
            "port": self._endpoint[1] if self._endpoint else None,
            "protocol": self._endpoint[2].get("protocol") if self._endpoint else None,
            "state": self._conn.state.name if self._conn else None,
            "connects": self.connects,
            "last_connected": self.last_connected,
        }

    def _connect(self) -> None:
        self._cancel_reconnect()
        self._drop()
        if self._endpoint is None or self._hub.transport is None:
            return
        host, port, txt = self._endpoint
        device = SyncleoUdpDevice.from_zeroconf(host, port, {**txt, "token": self._token})
        conn = _Connection(device, self._hub.transport, tz_offset=self._tz_offset)
        conn.register_callback(self._on_command)
        conn.register_state_callback(self._on_conn_state)
        self._conn = conn
        self._hub.attach(conn)
        asyncio.get_running_loop().create_task(conn.connect())

    def _drop(self) -> None:
        if (conn := self._conn) is None:
            return
        self._conn = None
        conn.unregister_callback(self._on_command)
        conn.unregister_state_callback(self._on_conn_state)
        conn.disconnect()
        self._hub.detach(conn)
        self._emit_state()

    def _on_command(self, cmd: UdpCommand) -> None:
        if changes := decode_udp(cmd):
            self._emit(changes)

    def _on_conn_state(self, state: ConnectionState) -> None:
        if state == ConnectionState.CONNECTED:
            self.connects += 1
            self.last_connected = time.time()
            self._backoff = RECONNECT_MIN
        elif state in (ConnectionState.DISCONNECTED, ConnectionState.NOT_CONNECTED) and self._running:
            # pysyncleo gives up for good after a few failures; we keep trying with a backoff.
            self._schedule_reconnect()
        self._emit_state()

    def _schedule_reconnect(self) -> None:
        if self._reconnect is not None:
            return
        delay, self._backoff = self._backoff, min(self._backoff * 2, RECONNECT_MAX)
        _LOGGER.debug("Local channel %s down, reconnecting in %.0fs", self.mac, delay)

        def fire() -> None:
            self._reconnect = None
            if self._running:
                self._connect()

        self._reconnect = asyncio.get_running_loop().call_later(delay, fire)

    def _cancel_reconnect(self) -> None:
        if self._reconnect is not None:
            self._reconnect.cancel()
            self._reconnect = None
