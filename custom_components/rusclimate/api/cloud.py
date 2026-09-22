"""Cloud channel: the vendor's MQTT broker, as the Hommyn app uses it. No Home Assistant imports.

One ``CloudHub`` holds a single MQTT session for all devices. It logs in with the app's own
credentials (baked into the Hommyn APK, identical for every user) and a unique
``Android <uuid>`` client id — the broker rejects other id formats with rc=2. Access to a device
is gated only by its share token, which is part of the topic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
import time
import uuid
from typing import Any

import aiomqtt

from . import params as p
from .channel import Channel, ChannelError

_LOGGER = logging.getLogger(__name__)

CLOUD_HOST = "mqtt.cloud.rusklimat.ru"
CLOUD_PORT = 8883
APP_USERNAME = "rusclimate_app"
APP_PASSWORD = "42fb1234ee9d1e4b"  # noqa: S105 — public constant shipped in every copy of the app
TOPIC_ROOT = "rusclimate"

RECONNECT_MIN = 5.0
RECONNECT_MAX = 300.0

# The device's last-will flag. It is retained and on type 69 can stay "true" after the module
# reconnects, so a live (non-retained) message from the device overrides it.
_CONNECTION_FLAG = "error/connection"


class CloudHub:
    def __init__(self, ssl_context: ssl.SSLContext, host: str = CLOUD_HOST, port: int = CLOUD_PORT) -> None:
        self._ssl = ssl_context
        self._host = host
        self._port = port
        self._client_id = "Android " + uuid.uuid4().hex
        self._channels: dict[str, CloudChannel] = {}  # topic prefix -> channel
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self.connected = False
        self.connects = 0
        self.last_error: str | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="rusclimate cloud mqtt")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._set_connected(False)

    async def attach(self, channel: CloudChannel) -> None:
        self._channels[channel.prefix] = channel
        if self._client is not None and self.connected:
            with contextlib.suppress(aiomqtt.MqttError):
                await self._client.subscribe(f"{channel.prefix}/state/#")
        self.start()

    async def detach(self, channel: CloudChannel) -> None:
        if self._channels.pop(channel.prefix, None) and self._client is not None and self.connected:
            with contextlib.suppress(aiomqtt.MqttError):
                await self._client.unsubscribe(f"{channel.prefix}/state/#")
        if not self._channels:
            await self.stop()

    @property
    def has_channels(self) -> bool:
        return bool(self._channels)

    async def publish(self, topic: str, payload: str) -> None:
        if self._client is None or not self.connected:
            raise ChannelError("cloud broker is not connected")
        try:
            # Never retain commands: a retained control message replays after a power cut.
            await self._client.publish(topic, payload, qos=0, retain=False)
        except aiomqtt.MqttError as err:
            raise ChannelError(f"cloud publish failed: {err}") from err

    async def _run(self) -> None:
        backoff = RECONNECT_MIN
        while True:
            try:
                async with aiomqtt.Client(
                    self._host,
                    self._port,
                    identifier=self._client_id,
                    username=APP_USERNAME,
                    password=APP_PASSWORD,
                    tls_context=self._ssl,
                    keepalive=60,
                    clean_session=True,
                ) as client:
                    self._client = client
                    for prefix in list(self._channels):
                        await client.subscribe(f"{prefix}/state/#")
                    self.connects += 1
                    self.last_error = None
                    backoff = RECONNECT_MIN
                    self._set_connected(True)
                    async for message in client.messages:
                        self._dispatch(message)
            except aiomqtt.MqttError as err:
                self.last_error = str(err)
                _LOGGER.debug("Cloud MQTT disconnected: %s; retry in %.0fs", err, backoff)
            finally:
                self._client = None
                self._set_connected(False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX)

    def _dispatch(self, message: aiomqtt.Message) -> None:
        topic = message.topic.value
        prefix, sep, key = topic.partition("/state/")
        if not sep or (channel := self._channels.get(prefix)) is None:
            return
        payload = message.payload
        text = payload.decode(errors="replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
        channel.handle(key, text, retained=bool(message.retain))

    def _set_connected(self, value: bool) -> None:
        if self.connected == value:
            return
        self.connected = value
        for channel in list(self._channels.values()):
            channel.hub_state_changed()


class CloudChannel(Channel):
    name = "cloud"

    def __init__(self, device_type: int, token: str, hub: CloudHub) -> None:
        super().__init__()
        self.prefix = f"{TOPIC_ROOT}/{device_type}/{token}"
        self._hub = hub
        self._device_online: bool | None = None
        self.last_live: float | None = None
        self.token_invalid = False

    @property
    def available(self) -> bool:
        return self._hub.connected and self._device_online is True

    async def start(self) -> None:
        await self._hub.attach(self)

    async def stop(self) -> None:
        await self._hub.detach(self)
        self._device_online = None

    async def send(self, key: str, value: Any) -> None:
        if not self.available:
            raise ChannelError("device is not online in the cloud")
        await self._hub.publish(f"{self.prefix}/control/{key}", p.encode_cloud(key, value))

    def handle(self, key: str, raw: str, retained: bool) -> None:
        was = self.available
        if key == _CONNECTION_FLAG:
            self._device_online = raw.strip().lower() != "true"
        elif key == "error/token_inv":
            self.token_invalid = raw.strip().lower() == "true"
        elif not retained:
            self.last_live = time.time()
            self._device_online = True
        if key not in (_CONNECTION_FLAG, "error/token_inv"):
            try:
                value = p.decode_cloud(key, raw)
            except ValueError, TypeError:
                _LOGGER.debug("Ignoring undecodable cloud value %s=%r", key, raw)
            else:
                self._emit({key: value})
        if self.available != was:
            self._emit_state()

    def hub_state_changed(self) -> None:
        if not self._hub.connected:
            self._device_online = None
        self._emit_state()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "broker_connected": self._hub.connected,
            "device_online_flag": self._device_online,
            "token_invalid": self.token_invalid,
            "last_live_message": self.last_live,
            "broker_connects": self._hub.connects,
            "broker_last_error": self._hub.last_error,
        }
