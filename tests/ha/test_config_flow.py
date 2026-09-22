from ipaddress import ip_address
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.rusclimate.const import DOMAIN

from .conftest import LINK, MAC, TOKEN, make_entry


def _no_setup():
    return patch("custom_components.rusclimate.async_setup_entry", return_value=True)


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with _no_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"share_link": LINK, "conn_mode": "local"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Office"
    assert result["data"] == {"mac": MAC, "device_type": 69, "token": TOKEN, "room": "Office"}
    assert result["options"] == {"conn_mode": "local"}
    assert result["result"].unique_id == MAC


async def test_user_flow_rejects_bad_and_unsupported_links(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"share_link": "hello"})
    assert result["errors"] == {"share_link": "invalid_link"}
    heater = LINK.replace("/69/", "/13/")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"share_link": heater})
    assert result["errors"] == {"share_link": "unsupported_device"}


def _discovery(mac=MAC, devtype="69"):
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.0.2.10"),
        ip_addresses=[ip_address("192.0.2.10")],
        hostname=f"{mac}.local.",
        name=f"{mac}._syncleo._udp.local.",
        port=41122,
        type="_syncleo._udp.local.",
        properties={
            "macaddr": ":".join(mac[i : i + 2] for i in range(0, 12, 2)),
            "devtype": devtype,
            "vendor": "RusClimate",
        },
    )


async def test_zeroconf_flow_requires_link_for_the_same_device(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_discovery()
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    other = LINK.replace(MAC, "112233445566")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"share_link": other})
    assert result["errors"] == {"share_link": "wrong_device"}
    with _no_setup():
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"share_link": LINK})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_zeroconf_ignores_other_device_types_and_known_devices(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_discovery(devtype="13")
    )
    assert result["reason"] == "not_supported"
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_discovery()
    )
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_token_only_for_same_device(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    wrong = LINK.replace(MAC, "112233445566")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"share_link": wrong})
    assert result["reason"] == "wrong_device"

    result = await entry.start_reconfigure_flow(hass)
    new_token = "f" * 32
    with _no_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"share_link": LINK.replace(TOKEN, new_token)}
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["token"] == new_token


async def test_options_flow_changes_mode(hass, channels):
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"conn_mode": "cloud"})
    await hass.async_block_till_done()
    assert entry.options == {"conn_mode": "cloud"}
    assert entry.runtime_data.breezer.mode.value == "cloud"
