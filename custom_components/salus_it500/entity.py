"""Base entity for the Salus iT500 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SalusCoordinator
from .model import Zone


def zone_key(zone: Zone, key: str) -> str:
    """Unique id suffix; zone 1 keeps the plain key used since v0.1."""
    return key if zone is Zone.ONE else f"zone2_{key}"


class SalusEntity(CoordinatorEntity[SalusCoordinator]):
    """Entity bound to one thermostat."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SalusCoordinator, key: str) -> None:
        super().__init__(coordinator)
        device_id = coordinator.device_id
        self._attr_unique_id = f"{device_id}_{key}"
        state = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=(state.description if state and state.description else f"Salus {MODEL}"),
            sw_version=state.firmware if state else None,
        )
