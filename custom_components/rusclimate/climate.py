"""The breezer as a climate entity: power, presets (device modes), fan speed, heater set point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .api import params as p
from .entity import RusclimateEntity
from .runtime import RusclimateConfigEntry

PARALLEL_UPDATES = 0

PRESETS: dict[str, p.Mode] = {
    "manual": p.Mode.MANUAL,
    "auto": p.Mode.AUTO,
    "night": p.Mode.NIGHT,
    "turbo": p.Mode.TURBO,
    "ventilation": p.Mode.VENTILATION,
}
PRESET_BY_MODE = {mode: name for name, mode in PRESETS.items()}
FAN_MODES = [str(s) for s in range(p.SPEED_MIN, p.SPEED_MAX + 1)]


async def async_setup_entry(
    hass: HomeAssistant, entry: RusclimateConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([BreezerClimate(entry)])


@dataclass
class _Extra(ExtraStoredData):
    last_on_mode: int

    def as_dict(self) -> dict[str, Any]:
        return {"last_on_mode": self.last_on_mode}


class BreezerClimate(RusclimateEntity, ClimateEntity, RestoreEntity):
    _attr_name = None
    _attr_translation_key = "breezer"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = p.TEMPERATURE_MIN
    _attr_max_temp = p.TEMPERATURE_MAX
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]  # noqa: RUF012
    _attr_fan_modes = FAN_MODES
    _watch = frozenset({p.MODE, p.SPEED, p.TARGET_TEMPERATURE, p.CURRENT_TEMPERATURE, p.PROGRAM_DATA_0})

    def __init__(self, entry: RusclimateConfigEntry) -> None:
        super().__init__(entry, "climate")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The device restores its own last mode on power-on, but we switch on by sending a mode,
        # so remember the last non-off mode across restarts (the device may be off at startup).
        extra = await self.async_get_last_extra_data()
        mode = extra.as_dict().get("last_on_mode") if extra else None
        if mode and self.state_data.get(p.MODE, p.Mode.OFF) == p.Mode.OFF:
            self.breezer.last_on_mode = int(mode)

    @property
    def extra_restore_state_data(self) -> _Extra:
        return _Extra(int(self.breezer.last_on_mode))

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.PRESET_MODE
        )
        if p.heater_installed(self.state_data) is not False:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def _mode(self) -> int | None:
        return self.state_data.get(p.MODE)

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._mode is None:
            return None
        return HVACMode.OFF if self._mode == p.Mode.OFF else HVACMode.FAN_ONLY

    @property
    def preset_modes(self) -> list[str]:
        # Auto is driven by the CO2 sensor; the device refuses it when none is fitted.
        has_co2 = p.co2_sensor_installed(self.state_data) is True
        return [name for name, mode in PRESETS.items() if mode != p.Mode.AUTO or has_co2]

    @property
    def preset_mode(self) -> str | None:
        return PRESET_BY_MODE.get(self._mode) if self._mode is not None else None

    @property
    def fan_mode(self) -> str | None:
        # Turbo reports 8, ventilation and off report 0: these are not user-selectable speeds.
        speed = self.state_data.get(p.SPEED)
        return str(speed) if speed is not None and p.SPEED_MIN <= speed <= p.SPEED_MAX else None

    @property
    def current_temperature(self) -> float | None:
        # Temperature of the supplied air, measured after the heater.
        return self.state_data.get(p.CURRENT_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        return self.state_data.get(p.TARGET_TEMPERATURE)

    async def async_turn_on(self) -> None:
        await self._send(p.MODE, int(self.breezer.last_on_mode))

    async def async_turn_off(self) -> None:
        await self._send(p.MODE, p.Mode.OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        elif self._mode in (None, p.Mode.OFF):
            await self.async_turn_on()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._send(p.MODE, PRESETS[preset_mode])

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._send(p.SPEED, int(fan_mode))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._send(p.TARGET_TEMPERATURE, float(temperature))
