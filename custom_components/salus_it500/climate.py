"""Climate entity for zone 1 of the iT500."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import SalusConfigEntry
from .entity import SalusEntity
from .model import Mode

PRESET_TEMP_HOLD = "temp_hold"

HVAC_TO_MODE = {HVACMode.OFF: Mode.OFF, HVACMode.HEAT: Mode.MANUAL, HVACMode.AUTO: Mode.AUTO}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the thermostat."""
    async_add_entities([SalusClimate(entry.runtime_data)])


class SalusClimate(SalusEntity, ClimateEntity):
    """Zone 1 thermostat.

    HEAT = manual mode, AUTO = schedule. A temporary hold (schedule paused at a
    manual setpoint) shows as AUTO with the temp_hold preset.
    """

    _attr_name = None
    _attr_translation_key = "thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_preset_modes = [PRESET_NONE, PRESET_TEMP_HOLD]
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_precision = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.room_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.setpoint

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self.coordinator.data.mode
        if mode is Mode.OFF:
            return HVACMode.OFF
        if mode is Mode.MANUAL:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        state = self.coordinator.data
        if state.heating:
            return HVACAction.HEATING
        return HVACAction.OFF if state.mode is Mode.OFF else HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        return PRESET_TEMP_HOLD if self.coordinator.data.mode is Mode.TEMP_HOLD else PRESET_NONE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        return {
            "salus_mode": state.mode.value,
            "frost_active": state.frost_active,
            "boost_hours": state.boost_hours,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get("hvac_mode")) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_temperature(float(temperature))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_set_mode(HVAC_TO_MODE[hvac_mode])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_TEMP_HOLD:
            await self.coordinator.async_set_mode(Mode.TEMP_HOLD)
        elif self.coordinator.data.mode is Mode.TEMP_HOLD:
            await self.coordinator.async_set_mode(Mode.AUTO)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_mode(Mode.MANUAL)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_mode(Mode.OFF)
