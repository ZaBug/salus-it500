"""Sensors for the Salus iT500."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import SalusConfigEntry
from .entity import SalusEntity
from .model import ThermostatState


def _last_report(state: ThermostatState) -> datetime | None:
    if not state.last_report_ms:
        return None
    return datetime.fromtimestamp(state.last_report_ms / 1000, tz=UTC)


@dataclass(frozen=True, kw_only=True)
class SalusSensorDescription(SensorEntityDescription):
    """Sensor with a value function."""

    value_fn: Callable[[ThermostatState], StateType | datetime]


SENSORS: tuple[SalusSensorDescription, ...] = (
    SalusSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda s: s.room_temperature,
    ),
    SalusSensorDescription(
        key="setpoint",
        translation_key="setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda s: s.setpoint,
    ),
    SalusSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_report,
    ),
    SalusSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.rssi,
    ),
    SalusSensorDescription(
        key="boost_hours",
        translation_key="boost_hours",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="h",
        value_fn=lambda s: s.boost_hours,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors."""
    coordinator = entry.runtime_data
    async_add_entities(SalusSensor(coordinator, description) for description in SENSORS)


class SalusSensor(SalusEntity, SensorEntity):
    """Value read from the thermostat state."""

    entity_description: SalusSensorDescription

    def __init__(self, coordinator, description: SalusSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)
