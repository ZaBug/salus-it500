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
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import SalusConfigEntry, SalusCoordinator
from .entity import SalusEntity, zone_key
from .model import ThermostatState, Zone, ZoneState


def _timestamp(ms: int) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, tz=UTC) if ms else None


@dataclass(frozen=True, kw_only=True)
class SalusZoneSensorDescription(SensorEntityDescription):
    """Sensor of one zone."""

    value_fn: Callable[[ZoneState], StateType]


@dataclass(frozen=True, kw_only=True)
class SalusSystemSensorDescription(SensorEntityDescription):
    """Sensor of the whole thermostat."""

    value_fn: Callable[[ThermostatState], StateType | datetime]


ZONE_SENSORS: tuple[SalusZoneSensorDescription, ...] = (
    SalusZoneSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda z: z.room_temperature,
    ),
    SalusZoneSensorDescription(
        key="setpoint",
        translation_key="setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda z: z.setpoint,
    ),
    SalusZoneSensorDescription(
        key="boost_hours",
        translation_key="boost_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda z: z.boost_hours,
    ),
)

SYSTEM_SENSORS: tuple[SalusSystemSensorDescription, ...] = (
    SalusSystemSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _timestamp(s.last_report_ms),
    ),
    SalusSystemSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        SalusZoneSensor(coordinator, zone, description)
        for zone in coordinator.data.zones
        for description in ZONE_SENSORS
    ]
    entities += [SalusSystemSensor(coordinator, description) for description in SYSTEM_SENSORS]
    async_add_entities(entities)


class SalusZoneSensor(SalusEntity, SensorEntity):
    """Value of one zone."""

    entity_description: SalusZoneSensorDescription

    def __init__(
        self, coordinator: SalusCoordinator, zone: Zone, description: SalusZoneSensorDescription
    ) -> None:
        super().__init__(coordinator, zone_key(zone, description.key))
        self.zone = zone
        self.entity_description = description
        if zone is Zone.TWO:
            self._attr_translation_key = f"zone2_{description.translation_key}"

    @property
    def available(self) -> bool:
        return super().available and self.zone in self.coordinator.data.zones

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data.zones[self.zone])


class SalusSystemSensor(SalusEntity, SensorEntity):
    """Value of the whole thermostat."""

    entity_description: SalusSystemSensorDescription

    def __init__(self, coordinator: SalusCoordinator, description: SalusSystemSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)
