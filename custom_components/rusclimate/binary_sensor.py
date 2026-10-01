"""Device fault flag; damper position (ASP-200S) in every mode."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import params as p
from .const import CONF_DEVICE_TYPE, PROFILES
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[BinarySensorEntity] = [ProblemSensor(entry)]
    if PROFILES[entry.data[CONF_DEVICE_TYPE]].purifier:
        entities.append(DamperPositionSensor(entry))
    async_add_entities(entities)


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


class DamperPositionSensor(RusclimateEntity, BinarySensorEntity):
    """Open or closed (recirculation), in every mode — the damper switch is only there in manual.

    The device reports damper "true" when it is closed (see switch.py).
    """

    _attr_device_class = BinarySensorDeviceClass.OPENING
    _attr_translation_key = "damper_position"
    _watch = frozenset({p.DAMPER})

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "damper_position")

    @property
    def is_on(self) -> bool | None:
        closed = self.state_data.get(p.DAMPER)
        return None if closed is None else not closed
