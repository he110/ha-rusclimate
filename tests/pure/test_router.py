"""Auto / Local / Cloud selection and fallback, on fake channels."""

import asyncio

import pytest

from rc.api import params as p
from rc.api import router as r
from rc.api.channel import Channel, ChannelError


class FakeChannel(Channel):
    def __init__(self, name: str, *, echo: bool = True) -> None:
        super().__init__()
        self.name = name
        self.up = False
        self.echo = echo
        self.fail_send = False
        self.sent: list[tuple[str, object]] = []

    @property
    def available(self) -> bool:
        return self.up

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, key, value):
        if self.fail_send or not self.up:
            raise ChannelError("down")
        self.sent.append((key, value))
        if self.echo:
            asyncio.get_running_loop().call_soon(self._emit, {key: value})

    def set_up(self, up: bool) -> None:
        self.up = up
        self._emit_state()

    def push(self, **changes) -> None:
        self._emit({k.replace("__", "/"): v for k, v in changes.items()})


@pytest.fixture
def chans():
    return FakeChannel("local"), FakeChannel("cloud")


@pytest.fixture(autouse=True)
def fast_echo(monkeypatch):
    monkeypatch.setattr(r, "ECHO_TIMEOUT", 0.05)


async def make(mode, local, cloud):
    b = r.Breezer(mode, local, cloud)
    await b.start()
    return b


async def test_auto_prefers_local_and_falls_back(chans):
    local, cloud = chans
    b = await make(r.ConnMode.AUTO, local, cloud)
    events = []
    b.add_listener(events.append)
    assert not b.available

    cloud.push(mode=1, speed=2)
    cloud.set_up(True)
    assert b.active is cloud and b.state[p.SPEED] == 2

    local.push(mode=1, speed=3)  # local is not active yet and cloud already knows speed: ignored
    assert b.state[p.SPEED] == 2
    local.set_up(True)
    assert b.active is local and b.state[p.SPEED] == 3
    assert r.CONNECTION_KEY in events[-1]

    local.set_up(False)
    assert b.active is cloud and b.state[p.SPEED] == 2  # cloud snapshot applied on switch


async def test_cloud_only_keys_fill_in_while_local_active(chans):
    local, cloud = chans
    b = await make(r.ConnMode.AUTO, local, cloud)
    local.push(mode=1)
    local.set_up(True)
    cloud.set_up(True)
    cloud.push(mode=0, diag__rssi=-40)
    assert b.state[p.MODE] == 1  # active channel wins
    assert b.state[p.RSSI] == -40  # local never reports it


async def test_local_mode_never_uses_cloud(chans):
    local, cloud = chans
    b = await make(r.ConnMode.LOCAL, local, cloud)
    cloud.set_up(True)
    assert b.cloud is None and not b.available
    with pytest.raises(r.NotAvailable):
        await b.send(p.MODE, 1)


async def test_send_goes_through_active(chans):
    local, cloud = chans
    b = await make(r.ConnMode.AUTO, local, cloud)
    local.set_up(True)
    cloud.set_up(True)
    await b.send(p.SPEED, 5)
    assert local.sent == [(p.SPEED, 5)] and cloud.sent == []
    await asyncio.sleep(0)
    assert b.state[p.SPEED] == 5


async def test_auto_retries_via_cloud_when_no_echo(chans):
    local, cloud = chans
    local.echo = False
    b = await make(r.ConnMode.AUTO, local, cloud)
    local.set_up(True)
    cloud.set_up(True)
    await b.send(p.MODE, 4)
    assert local.sent == [(p.MODE, 4)]
    assert cloud.sent == [(p.MODE, 4)]
    assert b.fallback_sends == 1


async def test_auto_uses_cloud_when_local_send_raises(chans):
    local, cloud = chans
    local.fail_send = True
    local.up = True
    b = await make(r.ConnMode.AUTO, local, cloud)
    cloud.set_up(True)
    await b.send(p.MODE, 3)
    assert cloud.sent == [(p.MODE, 3)]


async def test_strict_mode_does_not_retry(chans):
    local, cloud = chans
    local.echo = False
    b = await make(r.ConnMode.LOCAL, local, cloud)
    local.set_up(True)
    await b.send(p.MODE, 4)
    assert local.sent == [(p.MODE, 4)] and cloud.sent == []


async def test_remembers_last_on_mode(chans):
    local, cloud = chans
    b = await make(r.ConnMode.AUTO, local, cloud)
    local.set_up(True)
    local.push(mode=3)
    local.push(mode=0)
    assert b.last_on_mode == p.Mode.NIGHT


async def test_listener_gets_only_changed_keys(chans):
    local, cloud = chans
    b = await make(r.ConnMode.AUTO, local, cloud)
    local.set_up(True)
    seen = []
    b.add_listener(seen.append)
    local.push(mode=1, speed=2)
    local.push(mode=1, speed=2, time=10)
    assert seen == [{p.MODE, p.SPEED}, {p.TURBO_TIME}]
