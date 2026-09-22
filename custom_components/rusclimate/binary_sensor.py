"""Device fault flag."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import params as p
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ProblemSensor(entry)])


class ProblemSensor(RusclimateEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _watch = frozenset({p.ERROR_CODE})

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "problem")

    @property
    def is_on(self) -> bool | None:
        code = self.state_data.get(p.ERROR_CODE)
        return None if code is None else code != 0

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        code = self.state_data.get(p.ERROR_CODE)
        return {"error_code": code} if code else None
