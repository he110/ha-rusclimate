"""Config flow: one entry per device, added by its Hommyn share link (manually or from mDNS discovery)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api.router import ConnMode
from .api.share_link import InvalidShareLink, ShareLink, parse_share_link
from .const import (
    CONF_CONN_MODE,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    CONF_ROOM,
    CONF_SHARE_LINK,
    CONF_TOKEN,
    DOMAIN,
    SUPPORTED_DEVICE_TYPES,
)

_LINK = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_MODE = SelectSelector(
    SelectSelectorConfig(
        options=[m.value for m in ConnMode], mode=SelectSelectorMode.LIST, translation_key=CONF_CONN_MODE
    )
)


def _entry_data(link: ShareLink) -> dict[str, Any]:
    return {
        CONF_MAC: link.mac,
        CONF_DEVICE_TYPE: link.device_type,
        CONF_TOKEN: link.token,
        CONF_ROOM: link.room,
    }


def _title(link: ShareLink) -> str:
    return link.room or link.name or link.mac


class RusclimateConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_mac: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RusclimateOptionsFlow:
        return RusclimateOptionsFlow()

    def _parse(self, user_input: dict[str, Any], errors: dict[str, str]) -> ShareLink | None:
        try:
            link = parse_share_link(user_input[CONF_SHARE_LINK])
        except InvalidShareLink:
            errors[CONF_SHARE_LINK] = "invalid_link"
            return None
        if link.device_type not in SUPPORTED_DEVICE_TYPES:
            errors[CONF_SHARE_LINK] = "unsupported_device"
            return None
        return link

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and (link := self._parse(user_input, errors)):
            if self._discovered_mac and link.mac != self._discovered_mac:
                errors[CONF_SHARE_LINK] = "wrong_device"
            else:
                # A manual add must not be blocked by the pending discovery of the same device;
                # creating the entry aborts that discovery flow.
                await self.async_set_unique_id(link.mac, raise_on_progress=False)
                self._abort_if_unique_id_configured(updates=_entry_data(link))
                return self.async_create_entry(
                    title=_title(link),
                    data=_entry_data(link),
                    options={CONF_CONN_MODE: user_input.get(CONF_CONN_MODE, ConnMode.AUTO)},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SHARE_LINK): _LINK,
                    vol.Required(CONF_CONN_MODE, default=ConnMode.AUTO.value): _MODE,
                }
            ),
            errors=errors,
            description_placeholders={"mac": self._discovered_mac or ""},
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        props = discovery_info.properties
        mac = str(props.get("macaddr") or props.get("mac") or "").replace(":", "").lower()
        if len(mac) != 12:
            return self.async_abort(reason="not_supported")
        try:
            device_type = int(props.get("devtype", 0))
        except ValueError:
            device_type = 0
        if device_type not in SUPPORTED_DEVICE_TYPES:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        self._discovered_mac = mac
        self.context["title_placeholders"] = {"mac": mac}
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Paste a new share link, e.g. after the device was re-added in the app and got a new token."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None and (link := self._parse(user_input, errors)):
            await self.async_set_unique_id(link.mac)
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(entry, data_updates=_entry_data(link))
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_SHARE_LINK): _LINK}),
            errors=errors,
        )


class RusclimateOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_CONN_MODE, ConnMode.AUTO.value)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_CONN_MODE, default=current): _MODE}),
        )
