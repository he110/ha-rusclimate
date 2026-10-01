"""Ballu ONEAIR ASP-200S (device type 59): cloud only, speeds 1–8, PM2.5, pre-filter, purifier switches."""

from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.components.climate import HVACMode
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rusclimate.api import params as p
from custom_components.rusclimate.api.router import ConnMode
from custom_components.rusclimate.const import CONF_CONN_MODE, DOMAIN

from .conftest import LINK, MAC, TOKEN
from .test_config_flow import _no_setup

CLIMATE = "climate.office_breezer"

# Retained snapshot from a live ASP-200S (module firmware 1.21), decoded.
LIVE_STATE_59: dict[str, Any] = {
    p.MODE: 2,
    p.SPEED: 1,
    p.TARGET_TEMPERATURE: 18.0,
    p.CURRENT_TEMPERATURE: 15.0,
    p.CO2: 395,
    p.PM25: 4,
    p.EXPENDABLES: [98, 69],
    p.MELODY: 0,
    p.BUTTON_SOUND: False,
    p.BACKLIGHT_AUTO_OFF: True,
    p.IONIZER: False,
    p.UV_LAMP: False,
    p.DAMPER: False,
    p.TURBO_TIME: 0,
    p.PROGRAM_DATA_0: b"\x01\x01",
    p.PROGRAM_DATA_1: b"\x00\x01\x00\x01",
    p.ERROR_CODE: 0,
    p.FIRMWARE: "1.21",
}


def make_entry_59(mode: ConnMode = ConnMode.AUTO) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Office",
        unique_id=MAC,
        data={"mac": MAC, "device_type": 59, "token": TOKEN, "room": "Office"},
        options={CONF_CONN_MODE: mode.value},
    )


@pytest.fixture
async def loaded59(hass, channels):
    entry = make_entry_59()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    cloud = channels["cloud"]
    cloud.push(dict(LIVE_STATE_59))
    cloud.set_up(True)
    await hass.async_block_till_done()
    return entry, channels


@pytest.mark.parametrize("mode", [ConnMode.AUTO, ConnMode.LOCAL])
async def test_type_59_never_opens_a_local_channel(hass, channels, mode):
    # The local UDP codec is verified on type 69 only.
    entry = make_entry_59(mode)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert "local" not in channels
    assert entry.runtime_data.breezer.local is None
    assert entry.runtime_data.breezer.cloud is channels["cloud"]


async def test_climate_speeds_one_to_eight(hass, loaded59):
    _, ch = loaded59
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.FAN_ONLY
    assert state.attributes["preset_mode"] == "auto"
    assert state.attributes["fan_modes"] == [str(s) for s in range(1, 9)]
    await hass.services.async_call(
        "climate", "set_fan_mode", {"entity_id": CLIMATE, "fan_mode": "8"}, blocking=True
    )
    await hass.async_block_till_done()  # let the echo land before the next push
    assert ch["cloud"].sent == [(p.SPEED, 8)]
    assert hass.states.get(CLIMATE).attributes["fan_mode"] == "8"
    # Turbo reports 9: not a selectable speed.
    ch["cloud"].push({p.MODE: 4, p.SPEED: 9})
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).attributes["fan_mode"] is None


async def test_purifier_sensors(hass, loaded59):
    assert hass.states.get("sensor.office_breezer_pm2_5").state == "4"
    assert hass.states.get("sensor.office_breezer_filter").state == "98"
    assert hass.states.get("sensor.office_breezer_pre_filter").state == "69"
    assert hass.states.get("sensor.office_breezer_carbon_dioxide").state == "395"
    assert hass.states.get("select.office_breezer_sound") is None  # melody not verified on 59


async def test_ionizer_and_uv_switches(hass, loaded59):
    _, ch = loaded59
    assert hass.states.get("switch.office_breezer_ionizer").state == "off"
    assert hass.states.get("switch.office_breezer_uv_lamp").state == "off"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.office_breezer_ionizer"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.office_breezer_uv_lamp"}, blocking=True
    )
    await hass.async_block_till_done()
    assert ch["cloud"].sent == [(p.IONIZER, True), (p.UV_LAMP, True)]
    assert hass.states.get("switch.office_breezer_ionizer").state == "on"


async def test_damper_only_in_manual_mode(hass, loaded59):
    _, ch = loaded59
    damper = "switch.office_breezer_damper"
    assert hass.states.get(damper).state == STATE_UNAVAILABLE  # auto: the device drives it
    ch["cloud"].push({p.MODE: 1})
    await hass.async_block_till_done()
    # The fixture's damper is False on the wire, which the device means as open.
    assert hass.states.get(damper).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": damper}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(damper).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": damper}, blocking=True)
    await hass.async_block_till_done()
    assert ch["cloud"].sent == [(p.DAMPER, True), (p.DAMPER, False)]
    assert hass.states.get(damper).state == "on"


async def test_damper_reads_true_as_closed(hass, loaded59):
    # Owner, 2026-10-01: HA showed the damper open while the Hommyn app showed it closed,
    # and opening it in the app turned the HA switch off. "true" on the wire is closed.
    _, ch = loaded59
    damper = "switch.office_breezer_damper"
    ch["cloud"].push({p.MODE: 1, p.DAMPER: True})
    await hass.async_block_till_done()
    assert hass.states.get(damper).state == "off"
    ch["cloud"].push({p.DAMPER: False})
    await hass.async_block_till_done()
    assert hass.states.get(damper).state == "on"


def test_bools_go_out_as_digits():
    # control/damper "true" is ignored by the device; "1"/"0" work for every switch.
    for key in (p.IONIZER, p.UV_LAMP, p.DAMPER):
        assert p.encode_cloud(key, True) == "1"
        assert p.encode_cloud(key, False) == "0"


async def test_user_flow_accepts_asp200_link(hass):
    link = LINK.replace("/69/", "/59/")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with _no_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"share_link": link, CONF_CONN_MODE: ConnMode.AUTO.value}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["device_type"] == 59


async def test_damper_position_is_known_in_every_mode(hass, loaded59):
    # Owner, 2026-10-01: open vs closed (recirculation) matters whatever the mode, and the
    # damper switch is unavailable outside manual. The sensor reads the same inverted flag.
    _, ch = loaded59
    position = "binary_sensor.office_breezer_damper_position"
    assert hass.states.get("switch.office_breezer_damper").state == STATE_UNAVAILABLE  # auto
    assert hass.states.get(position).state == "on"  # fixture: damper False on the wire = open
    ch["cloud"].push({p.DAMPER: True})
    await hass.async_block_till_done()
    assert hass.states.get(position).state == "off"
