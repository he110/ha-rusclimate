"""Built-in ambient sound ("melody")."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import params as p
from .const import CONF_DEVICE_TYPE, PROFILES
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0

MELODIES = ["off", "rain", "sea", "forest", "birds", "fireplace"]  # index = device value


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    if PROFILES[entry.data[CONF_DEVICE_TYPE]].melody:
        async_add_entities([MelodySelect(entry)])


class MelodySelect(RusclimateEntity, SelectEntity):
    _attr_translation_key = "melody"
    _attr_options = MELODIES
    _watch = frozenset({p.MELODY})

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "melody")

    @property
    def current_option(self) -> str | None:
        value = self.state_data.get(p.MELODY)
        return MELODIES[value] if value is not None and 0 <= value < len(MELODIES) else None

    async def async_select_option(self, option: str) -> None:
        await self._send(p.MELODY, MELODIES.index(option))
