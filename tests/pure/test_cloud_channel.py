"""CloudChannel availability rules, without a broker."""

from rc.api import params as p
from rc.api.cloud import CloudChannel


class FakeHub:
    connected = True

    async def attach(self, channel):
        pass

    async def detach(self, channel):
        pass


def make():
    ch = CloudChannel(69, "0" * 32, FakeHub())
    states = []
    ch.bind(lambda c, changes: None, lambda c: states.append(c.available))
    return ch, states


def test_retained_snapshot_with_online_flag():
    ch, states = make()
    ch.handle("mode", "1", retained=True)
    assert not ch.available  # online unknown yet
    ch.handle("error/connection", "false", retained=True)
    assert ch.available and states == [True]
    assert ch.snapshot[p.MODE] == 1


def test_stale_offline_flag_is_overridden_by_live_message():
    ch, _ = make()
    ch.handle("error/connection", "true", retained=True)
    assert not ch.available
    ch.handle("speed", "3", retained=False)
    assert ch.available


def test_broker_loss_makes_channel_unavailable():
    ch, _ = make()
    ch.handle("error/connection", "false", retained=True)
    ch._hub.connected = False
    ch.hub_state_changed()
    assert not ch.available


def test_garbage_value_is_ignored():
    ch, _ = make()
    ch.handle("speed", "n/a", retained=False)
    assert p.SPEED not in ch.snapshot
