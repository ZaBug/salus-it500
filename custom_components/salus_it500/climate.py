"""Climate entities: zone 1, plus zone 2 on CH1+CH2 systems."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.climate import (
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import SalusConfigEntry, SalusCoordinator
from .entity import SalusEntity
from .model import MAX_BOOST_HOURS, MIN_BOOST_HOURS, Mode, Zone, ZoneState

PRESET_TEMP_HOLD = "temp_hold"
ATTR_HOURS = "hours"
SERVICE_BOOST = "boost"
SERVICE_CANCEL_BOOST = "cancel_boost"

HVAC_TO_MODE = {HVACMode.OFF: Mode.OFF, HVACMode.HEAT: Mode.MANUAL, HVACMode.AUTO: Mode.AUTO}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one climate entity per zone and the boost services."""
    coordinator = entry.runtime_data
    async_add_entities(SalusClimate(coordinator, zone) for zone in coordinator.data.zones)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_BOOST,
        {
            vol.Required(ATTR_HOURS): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_BOOST_HOURS, max=MAX_BOOST_HOURS)
            ),
            vol.Optional(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=MIN_TEMP, max=MAX_TEMP)
            ),
        },
        "async_boost",
    )
    platform.async_register_entity_service(SERVICE_CANCEL_BOOST, {}, "async_cancel_boost")


class SalusClimate(SalusEntity, ClimateEntity):
    """One heating zone.

    HEAT = manual mode, AUTO = schedule. A temporary hold (schedule paused at a
    manual setpoint) shows as AUTO with the temp_hold preset.
    """

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

    def __init__(self, coordinator: SalusCoordinator, zone: Zone) -> None:
        # Zone 1 keeps the unique id of v0.1 so existing entities are not recreated.
        super().__init__(coordinator, "climate" if zone is Zone.ONE else "zone2_climate")
        self.zone = zone
        if zone is Zone.ONE:
            self._attr_name = None
            self._attr_translation_key = "thermostat"
        else:
            self._attr_translation_key = "thermostat_zone2"

    @property
    def _zone(self) -> ZoneState:
        return self.coordinator.data.zones[self.zone]

    @property
    def available(self) -> bool:
        return super().available and self.zone in self.coordinator.data.zones

    @property
    def current_temperature(self) -> float | None:
        return self._zone.room_temperature

    @property
    def target_temperature(self) -> float | None:
        return self._zone.setpoint

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._zone.mode
        if mode is Mode.OFF:
            return HVACMode.OFF
        if mode is Mode.MANUAL:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        zone = self._zone
        if zone.heating:
            return HVACAction.HEATING
        return HVACAction.OFF if zone.mode is Mode.OFF else HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        return PRESET_TEMP_HOLD if self._zone.mode is Mode.TEMP_HOLD else PRESET_NONE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._zone
        return {
            "salus_mode": zone.mode.value,
            "frost_active": zone.frost_active,
            "boost_hours": zone.boost_hours,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get("hvac_mode")) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_temperature(float(temperature), self.zone)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_set_mode(HVAC_TO_MODE[hvac_mode], self.zone)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_TEMP_HOLD:
            await self.coordinator.async_set_mode(Mode.TEMP_HOLD, self.zone)
        elif self._zone.mode is Mode.TEMP_HOLD:
            await self.coordinator.async_set_mode(Mode.AUTO, self.zone)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_mode(Mode.MANUAL, self.zone)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_mode(Mode.OFF, self.zone)

    async def async_boost(self, hours: int, temperature: float | None = None) -> None:
        """Service salus_it500.boost."""
        await self.coordinator.async_boost(hours, temperature, self.zone)

    async def async_cancel_boost(self) -> None:
        """Service salus_it500.cancel_boost."""
        await self.coordinator.async_cancel_boost(self.zone)

