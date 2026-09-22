from pysyncleo.commands import UdpCommand
from pysyncleo.models import DiagnosticStatus

from rc.api import local
from rc.api import params as p


def cmd(hex_payload: str) -> UdpCommand:
    return UdpCommand.from_bytes(bytes.fromhex(hex_payload))


def test_decode_frames_seen_live():
    assert local.decode_udp(cmd("0103")) == {p.MODE: 3}
    assert local.decode_udp(cmd("0f08")) == {p.SPEED: 8}
    assert local.decode_udp(cmd("0b0400")) == {p.MELODY: 4}
    assert local.decode_udp(cmd("0901")) == {p.BUTTON_SOUND: True}
    assert local.decode_udp(cmd("034c040000")) == {p.TURBO_TIME: 1100}
    assert local.decode_udp(cmd("22" + "4c00")) == {p.EXPENDABLES: [76]}
    # program data: first byte is the block number
    assert local.decode_udp(cmd("42000100")) == {p.PROGRAM_DATA_0: b"\x01\x00"}
    assert local.decode_udp(cmd("4201000000")) == {p.PROGRAM_DATA_1: b"\x00\x00\x00"}


def test_decode_rssi_is_signed():
    diag = UdpCommand.from_bytes(bytes([0x88]))  # any DIAGNOSTIC-typed command
    diag.value = DiagnosticStatus(rssi=220)
    from pysyncleo.enums import UdpCommandType

    diag.command_type = UdpCommandType.DIAGNOSTIC
    assert local.decode_udp(diag) == {p.RSSI: -36}


def test_encode_round_trips_through_decode():
    for key, value in [
        (p.MODE, 5),
        (p.SPEED, 7),
        (p.TARGET_TEMPERATURE, 15.0),
        (p.MELODY, 2),
        (p.BUTTON_SOUND, False),
        (p.BACKLIGHT_AUTO_OFF, True),
        (p.PROGRAM_DATA_1, b"\x00\x02\x00"),
    ]:
        command = local.encode_udp(key, value)
        wire = bytes([command.command_type.value]) + command.serialize()
        assert local.decode_udp(UdpCommand.from_bytes(wire)) == {key: value}
