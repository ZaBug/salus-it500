"""Binary sensors for the Salus iT500."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SalusConfigEntry, SalusCoordinator
from .entity import SalusEntity, zone_key
from .model import ThermostatState, Zone, ZoneState


@dataclass(frozen=True, kw_only=True)
class SalusZoneBinaryDescription(BinarySensorEntityDescription):
    """Flag of one zone."""

    value_fn: Callable[[ZoneState], bool | None]


@dataclass(frozen=True, kw_only=True)
class SalusSystemBinaryDescription(BinarySensorEntityDescription):
    """Flag of the whole thermostat."""

    value_fn: Callable[[ThermostatState], bool | None]


ZONE_BINARY_SENSORS: tuple[SalusZoneBinaryDescription, ...] = (
    SalusZoneBinaryDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda z: z.heating,
    ),
    SalusZoneBinaryDescription(
        key="boost",
        translation_key="boost",
        value_fn=lambda z: z.boost_active,
    ),
    SalusZoneBinaryDescription(
        key="frost_protection",
        translation_key="frost_protection",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda z: z.frost_active,
    ),
)

SYSTEM_BINARY_SENSORS: tuple[SalusSystemBinaryDescription, ...] = (
    SalusSystemBinaryDescription(
        key="battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_low,
    ),
    SalusSystemBinaryDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.online,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        SalusZoneBinarySensor(coordinator, zone, description)
        for zone in coordinator.data.zones
        for description in ZONE_BINARY_SENSORS
    ]
    entities += [SalusSystemBinarySensor(coordinator, d) for d in SYSTEM_BINARY_SENSORS]
    async_add_entities(entities)


class SalusZoneBinarySensor(SalusEntity, BinarySensorEntity):
    """Flag of one zone."""

    entity_description: SalusZoneBinaryDescription

    def __init__(
        self, coordinator: SalusCoordinator, zone: Zone, description: SalusZoneBinaryDescription
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
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data.zones[self.zone])


class SalusSystemBinarySensor(SalusEntity, BinarySensorEntity):
    """Flag of the whole thermostat."""

    entity_description: SalusSystemBinaryDescription

    def __init__(self, coordinator: SalusCoordinator, description: SalusSystemBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
