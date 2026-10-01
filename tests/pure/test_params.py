import pytest

from rc.api import params as p

# Retained snapshot captured live from the office breezer (fixtures/phase0_kabinet_modes.log).
LIVE = {
    "expendables": "[76]",
    "sensor/temperature": "17.00",
    "sensor/co2": "0",
    "program_data/1": "000000",
    "program_data/0": "0100",
    "temperature": "5",
    "volume": "1",
    "mode": "1",
    "speed": "2",
    "error/code": "00",
    "backlight": "0",
    "diag/rssi": "-33",
    "amount": "0",
    "time": "900",
    "firmware": "1.38",
}


def test_decode_live_snapshot():
    state = {k: p.decode_cloud(k, v) for k, v in LIVE.items()}
    assert state[p.MODE] == p.Mode.MANUAL
    assert state[p.SPEED] == 2
    assert state[p.CURRENT_TEMPERATURE] == 17.0
    assert state[p.TARGET_TEMPERATURE] == 5.0
    assert state[p.BUTTON_SOUND] is True
    assert state[p.BACKLIGHT_AUTO_OFF] is False
    assert state[p.RSSI] == -33
    assert state[p.ERROR_CODE] == 0
    assert state[p.TURBO_TIME] == 900
    assert state[p.FIRMWARE] == "1.38"
    assert p.filter_percent(state) == 76
    assert p.heater_installed(state) is True
    assert p.co2_sensor_installed(state) is False


@pytest.mark.parametrize(
    ("key", "value", "wire"),
    [
        (p.MODE, p.Mode.NIGHT, "3"),
        (p.SPEED, 5, "5"),
        (p.TARGET_TEMPERATURE, 15.0, "15"),
        (p.BUTTON_SOUND, True, "1"),
        (p.BACKLIGHT_AUTO_OFF, False, "0"),
        (p.MELODY, 4, "4"),
        (p.PROGRAM_DATA_1, b"\x00\x02\x00", "000200"),
    ],
)
def test_encode_round_trip(key, value, wire):
    assert p.encode_cloud(key, value) == wire
    assert p.decode_cloud(key, wire) == value


def test_flags_unknown_until_program_data_arrives():
    assert p.heater_installed({}) is None
    assert p.co2_sensor_installed({p.PROGRAM_DATA_0: b"\x01"}) is None
    assert p.filter_percent({p.EXPENDABLES: []}) is None


# Retained snapshot from a live ASP-200S, device type 59, module firmware 1.21.
LIVE_59 = {
    "expendables": "[98,69]",
    "sensor/pm2": "4",
    "sensor/co2": "395",
    "ionizer": "true",
    "uv": "false",
    "damper": "false",
    "program_data/0": "0101",
    "program_data/1": "00010001",
    "speed": "9",
    "mode": "4",
}


def test_decode_asp200_snapshot():
    state = {k: p.decode_cloud(k, v) for k, v in LIVE_59.items()}
    assert state[p.PM25] == 4
    assert state[p.IONIZER] is True
    assert state[p.UV_LAMP] is False
    assert state[p.DAMPER] is False
    assert p.filter_percent(state) == 98
    assert p.filter_percent(state, 1) == 69
    assert p.filter_percent({p.EXPENDABLES: [76]}, 1) is None  # ASP-100 has one filter
    assert p.heater_installed(state) is True
    assert p.co2_sensor_installed(state) is True
