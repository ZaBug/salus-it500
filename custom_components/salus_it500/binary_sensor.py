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

from .coordinator import SalusConfigEntry
from .entity import SalusEntity
from .model import ThermostatState


@dataclass(frozen=True, kw_only=True)
class SalusBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor with a value function."""

    value_fn: Callable[[ThermostatState], bool | None]


BINARY_SENSORS: tuple[SalusBinarySensorDescription, ...] = (
    SalusBinarySensorDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda s: s.heating,
    ),
    SalusBinarySensorDescription(
        key="battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_low,
    ),
    SalusBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.online,
    ),
    SalusBinarySensorDescription(
        key="frost_protection",
        translation_key="frost_protection",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.frost_active,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(SalusBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class SalusBinarySensor(SalusEntity, BinarySensorEntity):
    """Flag read from the thermostat state."""

    entity_description: SalusBinarySensorDescription

    def __init__(self, coordinator, description: SalusBinarySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
