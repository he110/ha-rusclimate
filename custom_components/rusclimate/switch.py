"""Configuration switches: button beeps and backlight auto-off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import params as p
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0

SWITCHES = (
    SwitchEntityDescription(
        key=p.BUTTON_SOUND, translation_key="button_sound", entity_category=EntityCategory.CONFIG
    ),
    SwitchEntityDescription(
        key=p.BACKLIGHT_AUTO_OFF, translation_key="backlight_auto_off", entity_category=EntityCategory.CONFIG
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(RusclimateSwitch(entry, d) for d in SWITCHES)


class RusclimateSwitch(RusclimateEntity, SwitchEntity):
    def __init__(self, entry: RusclimateConfigEntry, description: SwitchEntityDescription) -> None:
        super().__init__(entry, description.translation_key or description.key)
        self.entity_description = description
        self._watch = frozenset({description.key})

    @property
    def is_on(self) -> bool | None:
        return self.state_data.get(self.entity_description.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(self.entity_description.key, False)
