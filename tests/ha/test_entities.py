from datetime import datetime

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.rusclimate.api import params as p
from custom_components.rusclimate.const import DOMAIN

from .conftest import LIVE_STATE, MAC, make_entry

CLIMATE = "climate.office_breezer"


def entity(hass):
    return hass.data["climate"].get_entity(CLIMATE)


async def test_climate_reflects_live_state(hass, loaded):
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.FAN_ONLY
    assert state.attributes["preset_mode"] == "manual"
    assert state.attributes["fan_mode"] == "2"
    assert state.attributes["current_temperature"] == 17.0
    assert state.attributes["temperature"] == 5.0
    # no CO2 sensor fitted -> no auto preset
    assert state.attributes["preset_modes"] == ["manual", "night", "turbo", "ventilation"]


async def test_turn_on_restores_last_mode(hass, loaded):
    _, ch = loaded
    local = ch["local"]
    local.push({p.MODE: 3})
    local.push({p.MODE: 0, p.SPEED: 0})
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).state == HVACMode.OFF
    await hass.services.async_call("climate", "turn_on", {"entity_id": CLIMATE}, blocking=True)
    assert local.sent[-1] == (p.MODE, 3)


async def test_presets_speed_and_temperature_commands(hass, loaded):
    _, ch = loaded
    local = ch["local"]
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": CLIMATE, "preset_mode": "turbo"}, blocking=True
    )
    await hass.services.async_call(
        "climate", "set_fan_mode", {"entity_id": CLIMATE, "fan_mode": "5"}, blocking=True
    )
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 15}, blocking=True
    )
    await hass.services.async_call("climate", "turn_off", {"entity_id": CLIMATE}, blocking=True)
    assert local.sent == [(p.MODE, 4), (p.SPEED, 5), (p.TARGET_TEMPERATURE, 15.0), (p.MODE, 0)]


async def test_turbo_speed_is_not_a_fan_mode_and_end_is_throttled(hass, loaded, freezer):
    _, ch = loaded
    local = ch["local"]
    local.push({p.MODE: 4, p.SPEED: 8, p.TURBO_TIME: 900})
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).attributes["fan_mode"] is None
    end = hass.states.get("sensor.office_breezer_turbo_ends")
    first = datetime.fromisoformat(end.state)
    written = end.last_updated
    for left in range(899, 890, -1):  # the device ticks once a second
        freezer.tick(1)
        local.push({p.TURBO_TIME: left})
    await hass.async_block_till_done()
    end = hass.states.get("sensor.office_breezer_turbo_ends")
    assert end.last_updated == written and datetime.fromisoformat(end.state) == first
    local.push({p.MODE: 1, p.SPEED: 2, p.TURBO_TIME: 0})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.office_breezer_turbo_ends").state == "unknown"


async def test_sensors_switches_select(hass, loaded):
    assert hass.states.get("sensor.office_breezer_filter").state == "76"
    assert hass.states.get("sensor.office_breezer_supply_air_temperature").state == "17.0"
    assert hass.states.get("sensor.office_breezer_carbon_dioxide").state == STATE_UNAVAILABLE  # not fitted
    assert hass.states.get("sensor.office_breezer_connection").state == "local"
    assert hass.states.get("switch.office_breezer_button_sound").state == "on"
    assert hass.states.get("switch.office_breezer_backlight_auto_off").state == "off"
    assert hass.states.get("select.office_breezer_sound").state == "off"
    assert hass.states.get("binary_sensor.office_breezer_problem").state == "off"

    _, ch = loaded
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.office_breezer_sound", "option": "birds"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.office_breezer_backlight_auto_off"}, blocking=True
    )
    assert ch["local"].sent == [(p.MELODY, 4), (p.BACKLIGHT_AUTO_OFF, True)]


async def test_falls_back_to_cloud_and_goes_unavailable(hass, loaded):
    _, ch = loaded
    local, cloud = ch["local"], ch["cloud"]
    cloud.push(dict(LIVE_STATE))
    cloud.set_up(True)
    local.set_up(False)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.office_breezer_connection").state == "cloud"
    await hass.services.async_call(
        "climate", "set_fan_mode", {"entity_id": CLIMATE, "fan_mode": "3"}, blocking=True
    )
    assert cloud.sent == [(p.SPEED, 3)]

    cloud.set_up(False)
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.office_breezer_connection").state == "offline"
    with pytest.raises(HomeAssistantError):
        await entity(hass).async_turn_on()


async def test_device_registry_and_unload(hass, loaded):
    entry, _ = loaded
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, MAC), entry.entry_id)
    assert device.sw_version == "1.38"
    assert device.name == "Breezer" and device.suggested_area == "Office"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert DOMAIN not in hass.data


async def test_local_only_entry_has_no_cloud_channel(hass, channels):
    from custom_components.rusclimate.api.router import ConnMode

    entry = make_entry(ConnMode.LOCAL)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert "cloud" not in channels
    assert entry.runtime_data.breezer.cloud is None
