"""Sensors: supply-air temperature, CO2, filter resource, turbo end, Wi-Fi signal, active channel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import params as p
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0

# The turbo countdown ticks every second; only move the end timestamp when it drifts this much.
TURBO_END_TOLERANCE = timedelta(seconds=5)


@dataclass(frozen=True, kw_only=True)
class RusclimateSensorDescription(SensorEntityDescription):
    watch: frozenset[str]
    value_fn: Callable[[dict[str, Any]], Any]
    available_fn: Callable[[dict[str, Any]], bool] = lambda _: True


SENSORS: tuple[RusclimateSensorDescription, ...] = (
    RusclimateSensorDescription(
        key="supply_temperature",
        translation_key="supply_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        watch=frozenset({p.CURRENT_TEMPERATURE}),
        value_fn=lambda s: s.get(p.CURRENT_TEMPERATURE),
    ),
    RusclimateSensorDescription(
        key="co2",
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        watch=frozenset({p.CO2, p.PROGRAM_DATA_0}),
        value_fn=lambda s: s.get(p.CO2),
        # Without the optional sensor the device reports a constant 0.
        available_fn=lambda s: p.co2_sensor_installed(s) is True,
    ),
    RusclimateSensorDescription(
        key="filter",
        translation_key="filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        watch=frozenset({p.EXPENDABLES}),
        value_fn=p.filter_percent,
    ),
    RusclimateSensorDescription(
        key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        watch=frozenset({p.RSSI}),
        value_fn=lambda s: s.get(p.RSSI),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        [
            *(RusclimateSensor(entry, d) for d in SENSORS),
            TurboEndSensor(entry),
            ConnectionSensor(entry),
        ]
    )


class RusclimateSensor(RusclimateEntity, SensorEntity):
    entity_description: RusclimateSensorDescription

    def __init__(self, entry: RusclimateConfigEntry, description: RusclimateSensorDescription) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description
        self._watch = description.watch

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(self.state_data)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.state_data)


class TurboEndSensor(RusclimateEntity, SensorEntity):
    """When turbo will end. The raw countdown is not exposed: it would write a state every second."""

    _attr_translation_key = "turbo_end"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _watch = frozenset({p.MODE, p.TURBO_TIME})

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "turbo_end")
        self._end: datetime | None = None

    def _on_breezer_update(self, changed: set[str]) -> None:
        end = self._compute()
        drifted = (end is None) != (self._end is None) or (
            end is not None and self._end is not None and abs(end - self._end) > TURBO_END_TOLERANCE
        )
        if drifted:
            self._end = end
            self.async_write_ha_state()
        elif changed - {p.TURBO_TIME}:
            super()._on_breezer_update(changed)

    def _compute(self) -> datetime | None:
        left = self.state_data.get(p.TURBO_TIME)
        if self.state_data.get(p.MODE) != p.Mode.TURBO or not left:
            return None
        return (dt_util.utcnow() + timedelta(seconds=left)).replace(microsecond=0)

    async def async_added_to_hass(self) -> None:
        self._end = self._compute()
        await super().async_added_to_hass()

    @property
    def native_value(self) -> datetime | None:
        return self._end


class ConnectionSensor(RusclimateEntity, SensorEntity):
    """Which channel currently carries the device: local, cloud or none."""

    _attr_translation_key = "connection"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["local", "cloud", "offline"]  # noqa: RUF012
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        active = self.breezer.active
        return active.name if active is not None else "offline"
