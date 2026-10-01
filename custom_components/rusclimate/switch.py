"""Switches: ionizer, UV lamp and damper (ASP-200S); configuration: button beeps and backlight auto-off."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import params as p
from .const import CONF_DEVICE_TYPE, PROFILES
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RusclimateSwitchDescription(SwitchEntityDescription):
    available_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    watch: frozenset[str] = frozenset()
    # The device's flag means the opposite of the switch: on in HA is false on the wire.
    inverted: bool = False


SWITCHES = (
    RusclimateSwitchDescription(
        key=p.BUTTON_SOUND, translation_key="button_sound", entity_category=EntityCategory.CONFIG
    ),
    RusclimateSwitchDescription(
        key=p.BACKLIGHT_AUTO_OFF, translation_key="backlight_auto_off", entity_category=EntityCategory.CONFIG
    ),
)

PURIFIER_SWITCHES = (
    RusclimateSwitchDescription(key=p.IONIZER, translation_key="ionizer"),
    RusclimateSwitchDescription(key=p.UV_LAMP, translation_key="uv_lamp"),
    # Outside manual mode the device drives the damper itself and ignores the command.
    # The device reports damper "true" when it is closed (checked against the Hommyn app,
    # 2026-10-01), so the switch is inverted: on means open.
    RusclimateSwitchDescription(
        key=p.DAMPER,
        translation_key="damper",
        inverted=True,
        available_fn=lambda s: s.get(p.MODE) == p.Mode.MANUAL,
        watch=frozenset({p.MODE}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    purifier = PROFILES[entry.data[CONF_DEVICE_TYPE]].purifier
    descriptions = (*SWITCHES, *(PURIFIER_SWITCHES if purifier else ()))
    async_add_entities(RusclimateSwitch(entry, d) for d in descriptions)


class RusclimateSwitch(RusclimateEntity, SwitchEntity):
    entity_description: RusclimateSwitchDescription

    def __init__(self, entry: RusclimateConfigEntry, description: RusclimateSwitchDescription) -> None:
        super().__init__(entry, description.translation_key or description.key)
        self.entity_description = description
        self._watch = frozenset({description.key}) | description.watch

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(self.state_data)

    @property
    def is_on(self) -> bool | None:
        raw = self.state_data.get(self.entity_description.key)
        return None if raw is None else raw != self.entity_description.inverted

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(self.entity_description.key, not self.entity_description.inverted)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(self.entity_description.key, self.entity_description.inverted)
